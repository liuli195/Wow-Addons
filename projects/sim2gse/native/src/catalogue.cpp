// 本模块不创建动作、不推进战斗、不更改执行计数。
#include "sim2gse/catalogue.hpp"
#include "simulationcraft.hpp"
#include "action/parse_effects.hpp"
#include <set>
#include "rapidjson/stringbuffer.h"
#include "rapidjson/writer.h"

namespace sim2gse
{
std::string unavailable_reason( const player_t& p, const std::string& signature,
                                const std::vector<unsigned>& spell_ids )
{
  for ( const auto& item : p.items )
  {
    if ( ( item.slot != SLOT_TRINKET_1 && item.slot != SLOT_TRINKET_2 ) ||
         signature != std::string( "use_item,slot=" ) + item.slot_name() ) continue;
    if ( item.special_effect( SPECIAL_EFFECT_SOURCE_NONE, SPECIAL_EFFECT_USE ) ||
         range::any_of( item.parsed.data.effects, []( const auto& entry ) {
           return entry.spell_id && entry.type == ITEM_SPELLTRIGGER_ON_USE;
         } ) ) return {};
    if ( !item.active() ) return "empty_slot";
    return item.parsed.data.id ? "passive_item" : std::string();
  }
  for ( const unsigned id : spell_ids )
  {
    const auto names = p.action_names_from_spell_id( id );
    if ( range::find( names, signature ) == names.end() ) continue;
    bool selected = false, unselected = false;
    for ( const auto tree : { talent_tree::CLASS, talent_tree::SPECIALIZATION, talent_tree::HERO } )
    {
      auto talent = p.find_talent_spell( tree, id, p.specialization() );
      if ( talent.invalid() )
      {
        const trait_data_t* match = nullptr;
        bool ambiguous = false;
        for ( const auto& trait : trait_data_t::data( util::class_id( p.type ), tree, p.is_ptr() ) )
        {
          if ( std::string( trait.name ) != p.find_spell( id )->name_cstr() ||
               range::find( trait.id_spec, static_cast<unsigned>( p.specialization() ) ) == trait.id_spec.end() )
            continue;
          if ( match ) { ambiguous = true; break; }
          match = &trait;
        }
        if ( match && !ambiguous ) talent = p.find_talent_spell( match->id_trait_node_entry );
      }
      if ( talent.invalid() ) continue;
      selected = selected || talent.enabled();
      unselected = unselected || !talent.enabled();
    }
    if ( unselected && !selected ) return "unselected_talent";
  }
  return {};
}

unsigned base_spell_id( const player_t& p, unsigned id )
{
  std::set<unsigned> seen;
  while (id && seen.insert(id).second)
  {
    unsigned base = id;
    for (const auto* buff : p.buff_list)
      for (const auto& effect : buff->data().effects())
        if (effect.type() == E_APPLY_AURA &&
            (effect.subtype() == A_OVERRIDE_ACTION_SPELL || effect.subtype() == A_OVERRIDE_ACTION_SPELL_TRIGGERED) &&
            effect.base_value() == id && effect.misc_value1() > 0)
          base = static_cast<unsigned>(effect.misc_value1());
    if (base == id) return id;
    id = base;
  }
  return 0;
}

bool action_available( const action_t& action )
{
  const auto& p = *action.player;
  const unsigned spell_id = action.data().id();
  if ( !spell_id || !action.data().ok() || !action.data().is_level( p.true_level ) ) return false;
  bool available = false, unselected = false;
  for ( const unsigned id : { spell_id, base_spell_id( p, spell_id ) } )
  {
    if ( !id ) continue;
    const auto* name = p.find_spell( id )->name_cstr();
    available = available || p.find_class_spell( name, p.specialization() )->id() == id ||
      p.find_specialization_spell( id, p.specialization() )->id() == id ||
      p.find_racial_spell( name )->id() == id;
    for ( const auto tree : { talent_tree::CLASS, talent_tree::SPECIALIZATION, talent_tree::HERO } )
    {
      const auto talent = p.find_talent_spell( tree, id, p.specialization() );
      if ( talent.invalid() ) continue;
      available = available || talent.enabled();
      unselected = unselected || !talent.enabled();
    }
  }
  return available && !unselected;
}

// eed909156 parse_effects.cpp: callbacks run before the inactive-buff shortcut.
// Full evaluation can mutate callback_idx; benefit=true also records buff usage.
bool static_effects_safe( const std::vector<player_effect_t>& effects, bool benefit )
{
  for ( const auto& effect : effects )
  {
    if ( effect.func || effect.value_func || ( benefit && effect.buff ) ) return false;
    if ( effect.simple ) continue;
    if ( effect.buff && !effect.buff->check() ) continue;
    if ( effect.idx || effect.mastery || ( effect.buff && ( effect.type & USE_CURRENT ) ) ) return false;
  }
  return true;
}

// The pinned class adapter certifies each getter before this serializer calls it.
// This runs once after native precombat initialization, before pre-pull actions.
void capture_static_snapshot( player_t& p, const std::vector<static_action_t>& entries,
                              const std::vector<const action_t*>& precombat_actions,
                              const std::map<std::string, double>& parameters,
                              const std::map<std::string, bool>& talents,
                              const std::map<std::string, std::string>& parameter_unknown )
{
  if ( !p.sim2gse_static_snapshot_json.empty() || p.is_pet() ) return;
  rapidjson::Document document;
  document.SetObject();
  js::JsonOutput root( document, document );
  root[ "protocol" ] = 1;
  root[ "stage" ] = "precombat_initialized_before_actions";
  root[ "collected_at_ms" ] = p.sim->current_time().total_millis();
  root[ "source" ] = "native initialized actor; action_t virtual arithmetic";
  auto hero_subtrees = root[ "hero_subtree_ids" ];
  hero_subtrees.make_array();
  for ( const auto id : p.player_sub_trees ) hero_subtrees.add( id );
  auto resources = root[ "resources" ];
  for ( resource_e resource = RESOURCE_NONE; resource < RESOURCE_MAX; resource++ )
  {
    if ( p.resources.max[ resource ] <= 0 ) continue;
    auto row = resources[ util::resource_type_string( resource ) ];
    row[ "current" ] = p.resources.current[ resource ];
    row[ "maximum" ] = p.resources.max[ resource ];
  }
  auto values = root[ "parameters" ];
  for ( const auto& entry : parameters ) values[ entry.first ] = entry.second;
  if ( !parameter_unknown.count( "precombat_gcd_ms" ) )
  {
    double gcd_ms = 0;
    for ( const auto* action : precombat_actions )
      gcd_ms = std::max( gcd_ms, static_cast<double>( action->gcd().total_millis() ) );
    values[ "precombat_gcd_ms" ] = gcd_ms;
  }
  for ( const auto& entry : talents ) values[ entry.first ] = entry.second;
  for ( const auto& entry : parameter_unknown ) root[ "parameter_unknown" ][ entry.first ] = entry.second;
  auto actions = root[ "actions" ];
  actions.make_array();
  for ( const auto& entry : entries )
  {
    auto* action = entry.action;
    const auto known = [ &entry ]( const char* field ) { return !entry.unknown.count( field ); };
    auto row = actions.add();
    row[ "name" ] = action->name_str;
    row[ "signature" ] = action->signature_str;
    row[ "action_list" ] = action->action_list ? action->action_list->name_str : "";
    row[ "spell_id" ] = action->data().id();
    row[ "base_spell_id" ] = base_spell_id( p, action->data().id() );
    row[ "background" ] = action->background;
    for ( const auto& unknown : entry.unknown ) row[ "unknown" ][ unknown.first ] = unknown.second;
    if ( known( "gcd_ms" ) ) row[ "gcd_ms" ] = action->gcd().total_millis();
    if ( known( "cooldown_ms" ) ) row[ "cooldown_ms" ] = action->cooldown_duration().total_millis();
    if ( known( "cast_ms" ) ) row[ "cast_ms" ] = action->execute_time().total_millis();
    row[ "channeled" ] = action->channeled;
    if ( action->cooldown )
    {
      row[ "charges" ] = action->cooldown->current_charge;
      row[ "max_charges" ] = action->cooldown->charges;
    }
    else
    {
      row[ "unknown" ][ "charges" ] = "missing_cooldown";
      row[ "unknown" ][ "max_charges" ] = "missing_cooldown";
    }
    if ( known( "costs" ) )
    {
      auto costs = row[ "costs" ];
      if ( entry.cost_action->current_resource() != RESOURCE_NONE )
        costs[ util::resource_type_string( entry.cost_action->current_resource() ) ] = action->cost();
    }
    const auto timing = action->energize_type_();
    row[ "gain_timing" ] = timing == action_energize::ON_CAST ? "on_cast" :
                            timing == action_energize::ON_HIT ? "on_hit" :
                            timing == action_energize::NONE ? "none" : "unknown";
    row[ "gain_status" ] = "unknown";
    // This is only the action's direct energize, never passive/pet/random resource income.
    row[ "gain_scope" ] = "direct_action";
    // Acquire the child only after adding parent members: AddMember can relocate them.
    auto gains = row[ "gains" ];
    if ( known( "gains" ) && timing == action_energize::NONE )
      row[ "gain_status" ] = "known_zero";
    else if ( known( "gains" ) && ( timing == action_energize::ON_CAST || timing == action_energize::ON_HIT ) &&
              action->energize_resource_() != RESOURCE_NONE )
    {
      auto* state = action->get_state();
      state->target = action->target;
      state->n_targets = 1;
      state->chain_target = 0;
      gains[ util::resource_type_string( action->energize_resource_() ) ] =
        action->composite_energize_amount( state );
      action_state_t::release( state );
      row[ "gain_status" ] = "known";
    }
  }
  rapidjson::StringBuffer buffer;
  rapidjson::Writer<rapidjson::StringBuffer> writer( buffer );
  document.Accept( writer );
  p.sim2gse_static_snapshot_json.assign( buffer.GetString(), buffer.GetSize() );
}

void write_player_report( js::JsonOutput root, const player_t& p, bool include_apl )
{
  if ( !p.sim2gse_static_snapshot_json.empty() )
  {
    rapidjson::Document snapshot;
    snapshot.Parse( p.sim2gse_static_snapshot_json.c_str() );
    root[ "sim2gse_static_snapshot" ].val().CopyFrom( snapshot, root.doc().GetAllocator() );
  }
  root[ "sim2gse_class" ] = util::player_type_string( p.type );
  root[ "sim2gse_class_id" ] = util::class_id( p.type );
  root[ "sim2gse_spec_id" ] = static_cast<unsigned>( p.specialization() );
  root[ "sim2gse_spec" ] = dbc::specialization_string( p.specialization() );
  root[ "sim2gse_resource" ] = util::resource_type_string( p.primary_resource() );
  root[ "sim2gse_actions_protocol" ] = 1;
  auto actions = root[ "sim2gse_actions" ];
  actions.make_array();
  for ( const auto* a : p.action_list )
  {
    if ( !a->total_executions ) continue;
    auto row = actions.add();
    row[ "name" ] = a->name_str;
    row[ "id" ] = a->id;
    row[ "data_id" ] = a->data().id();
    row[ "base_spell_id" ] = sim2gse::base_spell_id( p, a->data().id() );
    row[ "data_valid" ] = a->data().ok();
    row[ "signature" ] = a->signature_str;
    row[ "executions" ] = a->total_executions;
    row[ "type" ] = util::action_type_string( a->type );
    row[ "background" ] = a->background;
    row[ "quiet" ] = a->quiet;
    row[ "harmful" ] = a->harmful;
    row[ "player_owned" ] = a->player == &p && !p.is_pet();
    row[ "passive" ] = a->data().flags( SX_PASSIVE );
    row[ "action_list" ] = a->action_list ? a->action_list->name_str : "";
    row[ "precombat" ] = a->is_precombat;
    row[ "gcd_ms" ] = a->trigger_gcd.total_millis();
    row[ "cast_ms" ] = a->execute_time().total_millis();
    row[ "channeled" ] = a->channeled;
  }
  if ( include_apl )
  {
    // Search every instantiated combat APL entry, including branches pruned from foreground lists.
    // Existing executed-action counters and the simulation itself remain unchanged.
    root[ "sim2gse_apl_actions_protocol" ] = 1;
    auto apl_actions = root[ "sim2gse_apl_actions" ];
    apl_actions.make_array();
    for ( const auto* a : p.action_list )
    {
      // use_items creates background proxies with a real slot signature (patch 012).
      const bool item_proxy = a->signature_str.find( "use_item,slot=" ) == 0;
      if ( a->is_precombat || ( !a->action_list && !item_proxy ) )
        continue;
  
      const unsigned spell_id = a->data().id();
      const unsigned base_spell_id = sim2gse::base_spell_id( p, spell_id );
      const auto* spell_name = a->data().name_cstr();
      const bool class_spell = p.find_class_spell( spell_name, p.specialization() )->id() == spell_id;
      const bool specialization_spell =
        p.find_specialization_spell( spell_id, p.specialization() )->id() == spell_id;
      const bool racial_spell = p.find_racial_spell( spell_name )->id() == spell_id;
      bool selected_talent = false;
      bool unselected_talent = false;
      for ( const auto tree : { talent_tree::CLASS, talent_tree::SPECIALIZATION, talent_tree::HERO } )
      {
        for ( const unsigned candidate_id : { spell_id, base_spell_id } )
        {
          const auto talent = p.find_talent_spell( tree, candidate_id, p.specialization() );
          if ( !talent.invalid() )
          {
            selected_talent = selected_talent || talent.enabled();
            unselected_talent = unselected_talent || !talent.enabled();
          }
        }
      }
      const bool special_button = a->name_str == "auto_attack" ||
        a->signature_str.find( "use_item," ) == 0;
  
      auto row = apl_actions.add();
      row[ "name" ] = a->name_str;
      row[ "id" ] = a->id;
      row[ "data_id" ] = spell_id;
      row[ "base_spell_id" ] = base_spell_id;
      row[ "data_valid" ] = a->data().ok();
      row[ "signature" ] = a->signature_str;
      row[ "executions" ] = a->total_executions;
      row[ "type" ] = util::action_type_string( a->type );
      row[ "background" ] = a->background;
      row[ "quiet" ] = a->quiet;
      row[ "harmful" ] = a->harmful;
      row[ "player_owned" ] = a->player == &p && !p.is_pet();
      row[ "passive" ] = a->data().flags( SX_PASSIVE );
      row[ "action_list" ] = a->action_list ? a->action_list->name_str : "";
      row[ "precombat" ] = false;
      row[ "gcd_ms" ] = a->trigger_gcd.total_millis();
      row[ "action_initialized" ] = a->initialized;
      row[ "available" ] = special_button || ( spell_id && a->data().is_level( p.true_level ) &&
        !unselected_talent && ( class_spell || specialization_spell || racial_spell || selected_talent ) );
    }
  }
  auto precombat_actions = root[ "sim2gse_precombat_actions" ];
  precombat_actions.make_array();
  for ( const auto* a : p.precombat_action_list )
  {
    auto row = precombat_actions.add();
    row[ "name" ] = a->name_str;
    row[ "id" ] = a->id;
    row[ "data_id" ] = a->data().id();
    row[ "base_spell_id" ] = sim2gse::base_spell_id( p, a->data().id() );
    row[ "data_valid" ] = a->data().ok();
    row[ "signature" ] = a->signature_str;
    row[ "executions" ] = a->total_executions;
    row[ "type" ] = util::action_type_string( a->type );
    row[ "background" ] = a->background;
    row[ "quiet" ] = a->quiet;
    row[ "harmful" ] = a->harmful;
    row[ "player_owned" ] = a->player == &p && !p.is_pet();
    row[ "passive" ] = a->data().flags( SX_PASSIVE );
    row[ "action_list" ] = a->action_list ? a->action_list->name_str : "";
    row[ "precombat" ] = true;
    row[ "gcd_ms" ] = a->trigger_gcd.total_millis();
    row[ "cast_ms" ] = a->execute_time().total_millis();
    row[ "channeled" ] = a->channeled;
  }
  auto items = root[ "sim2gse_items" ];
  items.make_array();
  for ( const auto& item : p.items )
  {
    const auto* effect = item.special_effect( SPECIAL_EFFECT_SOURCE_NONE, SPECIAL_EFFECT_USE );
    if ( !effect ) continue;
    auto row = items.add();
    row[ "slot" ] = item.slot_name();
    row[ "id" ] = item.parsed.data.id;
    row[ "driver_spell_id" ] = effect->driver()->id();
    row[ "name" ] = item.name_str;
    row[ "channeled" ] = ( effect->execute_action && effect->execute_action->channeled ) ||
      effect->driver()->flags( SX_CHANNELED ) || effect->driver()->flags( SX_CHANNELED_2 );
  }

  // Report evidence of permanent unavailability separately from runtime readiness.
  root[ "sim2gse_availability_protocol" ] = 1;
  auto unavailable = root[ "sim2gse_unavailable_actions" ];
  unavailable.make_array();
  for ( const auto& item : p.items )
  {
    if ( item.slot != SLOT_TRINKET_1 && item.slot != SLOT_TRINKET_2 ) continue;
    const auto reason = unavailable_reason( p, std::string( "use_item,slot=" ) + item.slot_name() );
    if ( reason.empty() ) continue;
    auto row = unavailable.add();
    row[ "kind" ] = "item";
    row[ "slot" ] = item.slot == SLOT_TRINKET_1 ? 13 : 14;
    row[ "item_id" ] = item.parsed.data.id;
    row[ "reason" ] = reason;
  }

}

void write_damage_owner( js::JsonOutput node, const stats_t& s )
{
  node[ "sim2gse_actor_index" ] = s.player->actor_index;
  node[ "sim2gse_actor_name" ] = s.player->name_str;
  node[ "sim2gse_owner_type" ] = s.player->is_pet() ? "owned_unit" : "player";
}
}
