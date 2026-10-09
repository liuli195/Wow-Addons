// 本模块不创建动作、不推进战斗、不更改执行计数。
#include "sim2gse/catalogue.hpp"
#include "simulationcraft.hpp"
#include <set>

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

void write_player_report( js::JsonOutput root, const player_t& p, bool include_apl )
{
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
