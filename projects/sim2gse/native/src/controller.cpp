#include "controller.hpp"
#include "catalogue.hpp"
#include "simulationcraft.hpp"
#include <typeinfo>

namespace sim2gse
{
void controller_t::register_options( player_t& owner )
{
  owner_ = &owner;
  owner.add_option( opt_string("sim2gse_steps", sim2gse_steps) );
  owner.add_option( opt_string("sim2gse_rule_observations", observation_request_) );
  owner.add_option( opt_string("sim2gse_optional_spells", optional_spell_ids_) );
  owner.add_option( opt_string("sim2gse_castsequences", sim2gse_castsequences) );
  owner.add_option( opt_string("sim2gse_castsequence_events", sim2gse_castsequence_events) );
  owner.add_option( opt_string("sim2gse_times", sim2gse_times) );
  owner.add_option( opt_string("sim2gse_sources", input_sources_text_) );
  owner.add_option( opt_uint("sim2gse_burst_offset", burst_offset_, 0, 4096) );
  owner.add_option( opt_string("sim2gse_gcd_states", sim2gse_gcd_states) );
  owner.add_option( opt_string("sim2gse_failed_actions", sim2gse_failed_actions) );
  owner.add_option( opt_string("sim2gse_failure_events", sim2gse_failure_events) );
  owner.add_option( opt_bool("sim2gse_timed_feedback", sim2gse_timed_feedback) );
  owner.add_option( opt_bool("sim2gse_trace", sim2gse_trace) );
  owner.add_option( opt_timespan("sim2gse_window", sim2gse_window) );
}

void controller_t::initialize( player_t& owner )
{
  owner_ = &owner;
  sim2gse_init();
}

void controller_t::initialize_times()
{
  for (auto value : util::string_split(sim2gse_times, "/"))
  {
    if (value.empty() || value.find_first_not_of("0123456789") != std::string::npos)
      throw std::runtime_error("invalid sim2gse input time");
    auto at = timespan_t::from_millis(std::stoul(value));
    if (at >= owner_->sim->max_time || (!input_times_.empty() && at <= input_times_.back()))
      throw std::runtime_error("sim2gse input times must increase within combat");
    input_times_.push_back(at);
  }
  if (input_times_.size() > 4096)
    throw std::runtime_error("too many sim2gse input times");
  for (auto value : util::string_split(sim2gse_gcd_states, "/"))
  {
    if (value.empty()) continue;
    const auto fields = util::string_split(value, ",");
    if (fields.size() != 2 ||
        fields[0].find_first_not_of("0123456789") != std::string::npos ||
        fields[1].find_first_not_of("0123456789") != std::string::npos)
      throw std::runtime_error("invalid sim2gse GCD feedback");
    sim2gse_observed_gcd_states.emplace_back(
        timespan_t::from_millis(std::stoul(fields[0])),
        timespan_t::from_millis(std::stoul(fields[1])));
  }
  if (!sim2gse_observed_gcd_states.empty() &&
      sim2gse_observed_gcd_states.size() != input_times_.size())
    throw std::runtime_error("sim2gse GCD feedback must match input times");
  for (auto value : util::string_split(sim2gse_failed_actions, "/"))
    sim2gse_observed_failed_actions.push_back(value == "-" ? "" : value);
  if (!sim2gse_observed_failed_actions.empty() &&
      sim2gse_observed_failed_actions.size() != input_times_.size())
    throw std::runtime_error("sim2gse failure feedback must match input times");
  if (!sim2gse_failed_actions.empty() && !sim2gse_failure_events.empty())
    throw std::runtime_error("sim2gse failure feedback formats cannot be mixed");
  for (auto value : util::string_split(sim2gse_failure_events, "/"))
  {
    if (value.empty()) continue;
    const auto fields = util::string_split(value, ",");
    if (fields.size() != 3 || fields[0].empty() || fields[1].empty() || fields[2].empty() ||
        fields[0].find_first_not_of("0123456789") != std::string::npos ||
        fields[1].find_first_not_of("0123456789") != std::string::npos)
      throw std::runtime_error("invalid sim2gse failure event");
    const auto at = timespan_t::from_millis(std::stoul(fields[0]));
    const auto from = static_cast<unsigned>(std::stoul(fields[1]));
    if (at >= owner_->sim->max_time || from == 0 || from > input_times_.size() ||
        at < input_times_[from - 1])
      throw std::runtime_error("sim2gse failure event precedes its input or exceeds combat");
    sim2gse_observed_failure_events.emplace_back(at, from, fields[2]);
  }
}

void controller_t::initialize_sources()
{
  if (input_sources_text_.empty())
  {
    if (burst_offset_) throw std::runtime_error("burst offset requires input sources");
    return;
  }
  const auto sources = util::string_split(input_sources_text_, "/");
  if (sources.size() != input_times_.size() || !burst_offset_ || burst_offset_ >= sim2gse_blocks.size())
    throw std::runtime_error("invalid sim2gse input source configuration");
  unsigned loop = 0, burst = 0;
  for (const auto& source : sources)
  {
    if (source != "loop" && source != "burst")
      throw std::runtime_error("unknown sim2gse input source");
    const bool is_burst = source == "burst";
    auto& position = is_burst ? burst : loop;
    const auto offset = is_burst ? burst_offset_ : 0u;
    const auto count = is_burst ? sim2gse_blocks.size() - burst_offset_ : burst_offset_;
    input_steps_.push_back(offset + position % count);
    source_origins_.push_back(++position);
    burst_inputs_.push_back(is_burst);
  }
}

unsigned controller_t::step_for_origin( unsigned origin ) const
{
  if (!input_steps_.empty()) return input_steps_.at(origin - 1);
  return (origin - 1) % sim2gse_blocks.size();
}

void controller_t::reset( player_t& owner )
{
  owner_ = &owner;

  input_ = 0;
  sim2gse_step = sim2gse_pending_origin = sim2gse_committed_origin = sim2gse_origin = 0;
  for (auto& [step, position] : sim2gse_castsequence_positions) position = 0;
  sim2gse_castsequence_pending_origins.clear();
  sim2gse_castsequence_origin_members.clear();
  sim2gse_castsequence_generations.clear();
  sim2gse_castsequence_origin_generations.clear();
  sim2gse_castsequence_last_use.clear();
  sim2gse_castsequence_clock_started = false;
  sim2gse_precombat_gcd = sim2gse_precombat_cast = sim2gse_precombat_cast_ready = 0_ms;
  sim2gse_client_gcd_ready = 0_ms;
  sim2gse_last_observed_gcd_start = sim2gse_last_observed_gcd_duration = 0_ms;
  sim2gse_observed_gcd_initialized = false;
  sim2gse_tentative_gcd_start = sim2gse_tentative_gcd_duration = sim2gse_tentative_old_gcd_start =
    sim2gse_tentative_old_gcd_duration = 0_ms;
  sim2gse_tentative_stable_reads = 0;
  sim2gse_tentative_gcd = false;
  sim2gse_waiting_confirmation = false;
  sim2gse_confirmed_tentative_gcd = false;
  sim2gse_confirmed_tentative_origin = 0;
  sim2gse_confirmed_tentative_action = nullptr;
  sim2gse_pending = sim2gse_committed = sim2gse_dispatch = nullptr;
  sim2gse_candidates.clear();
  sim2gse_executed_actions.clear();
  issued_actions_.clear();
  sim2gse_deferred_dispatches.clear();
  sim2gse_commit = sim2gse_queue = nullptr;
  observation_active_ = false;
  observation_execution_origins_.clear();
  observation_counted_actions_.clear();
  observation_buffs_.clear();
  observation_buffs_active_ = false;
  observation_dots_.clear();
  observation_dot_coverage_.clear();
  observation_dots_active_ = false;
}

void controller_t::start( player_t& owner )
{
  owner_ = &owner;
  if ( !enabled() ) return;
  start_observations();

    for (const auto& [at, flag] : sim2gse_castsequence_reset_events)
    {
      if (flag & (4 | 8 | 16)) continue;  // Modifiers reset on the matching click.
      make_event(*owner_->sim, at, [this, flag] {
        for (const auto& [step, members] : sim2gse_castsequence_members)
          if (flag == 32 || (sim2gse_castsequence_reset_flags[step] & flag))
            sim2gse_reset_castsequence(step);
      });
    }
    schedule_first_input();
    for (const auto& [at, from, name] : sim2gse_observed_failure_events)
    {
      auto handle_failure = [this, from, name] {
        action_t* matched = nullptr;
        const auto deferred = std::find_if(sim2gse_deferred_dispatches.begin(), sim2gse_deferred_dispatches.end(),
            [from, &name](const auto& entry) {
              return entry.first.first == from && entry.first.second->name_str == name;
            });
        if (deferred != sim2gse_deferred_dispatches.end())
        {
          matched = deferred->first.second;
          event_t::cancel(deferred->second);
          sim2gse_deferred_dispatches.erase(deferred);
          handle_event("observed_failed", matched, from);
          return;
        }
        const auto candidate = std::find_if(sim2gse_candidates.begin(), sim2gse_candidates.end(),
            [from, &name](const auto& entry) { return entry.second == from && entry.first->name_str == name; });
        if (candidate != sim2gse_candidates.end())
        {
          matched = candidate->first;
          const bool was_pending = sim2gse_pending == matched && sim2gse_pending_origin == from;
          const bool was_committed = sim2gse_committed == matched && sim2gse_committed_origin == from;
          sim2gse_candidates.erase(candidate);
          if (was_pending)
          {
            event_t::cancel(sim2gse_commit);
            sim2gse_pending = sim2gse_candidates.empty() ? nullptr : sim2gse_candidates.back().first;
            if (sim2gse_pending)
            {
              sim2gse_pending_origin = sim2gse_candidates.back().second;
              handle_event("queue_restore", sim2gse_pending, sim2gse_pending_origin);
              sim2gse_arm_queue();
            }
          }
          if (was_committed)
          {
            event_t::cancel(sim2gse_queue);
            sim2gse_committed = sim2gse_candidates.empty() ? nullptr : sim2gse_candidates.back().first;
            sim2gse_waiting_confirmation = false;
            if (sim2gse_committed)
            {
              sim2gse_committed_origin = sim2gse_candidates.back().second;
              handle_event("queue_restore", sim2gse_committed, sim2gse_committed_origin);
              sim2gse_execute_committed();
            }
            else
            {
              handle_event("queue_rollback", matched, from);
              sim2gse_tentative_gcd = false;
              sim2gse_tentative_stable_reads = 0;
              sim2gse_client_gcd_ready = sim2gse_tentative_old_gcd_start + sim2gse_tentative_old_gcd_duration;
            }
          }
        }
        else if (sim2gse_pending && sim2gse_pending_origin == from && sim2gse_pending->name_str == name)
        {
          matched = sim2gse_pending;
          event_t::cancel(sim2gse_commit);
          sim2gse_pending = nullptr;
        }
        else if (std::any_of(sim2gse_executed_actions.begin(), sim2gse_executed_actions.end(),
                 [from, &name](const auto& executed) {
                   return executed.first == from && executed.second->name_str == name;
                 }))
          handle_event("late_negative_feedback", nullptr, from);
        handle_event("observed_failed", matched, from);
      };
      if (matches_input_time( at, from ))
        make_event(*owner_->sim, at, [this, handle_failure] { make_event(*owner_->sim, 0_ms, handle_failure); });
      else
        make_event(*owner_->sim, at, handle_failure);
    }
  }

void controller_t::schedule_first_input()
{

  make_event( *owner_->sim, input_times_.empty() ? 0_ms : input_times_.front(),
              [this] { sim2gse_tick(); } );
}

void controller_t::schedule_next()
{

  if ( input_times_.empty() )
    make_event( *owner_->sim, 300_ms, [this] { sim2gse_tick(); } );
  else if ( input_ < input_times_.size() )
    make_event( *owner_->sim, input_times_[input_] - owner_->sim->current_time(),
                [this] { sim2gse_tick(); } );
}

bool controller_t::matches_input_time( timespan_t at, unsigned origin ) const
{
  return at == input_times_[origin - 1];
}

selection_t controller_t::select()
{
  if ( !enabled() ) return { selection_kind::uncontrolled, nullptr };
  auto* selected = sim2gse_dispatch;
  sim2gse_dispatch = nullptr;
  return { selected ? selection_kind::selected : selection_kind::controlled_idle, selected };
}

void controller_t::notify( const char* event, action_t* action, unsigned origin )
{
  if ( enabled() ) handle_event( event, action, origin );
}

void controller_t::transfer_replacement( action_t* from, action_t* to )
{
  if ( !enabled() || !sim2gse_origin ) return;
  const auto issued = issued_actions_.find( { sim2gse_origin, from } );
  if ( issued == issued_actions_.end() ) return; // Derived actions cannot authorize a replacement.
  const auto [found, inserted] = issued_actions_.emplace(
    std::make_pair( sim2gse_origin, to ), issued->second );
  if ( !inserted && found->second != issued->second )
    throw std::runtime_error("sim2gse native replacement has conflicting issued actions");
}

void controller_t::precombat( action_t& action, precombat_phase phase )
{
  if ( !enabled() ) return;
  if ( phase == precombat_phase::before )
    handle_event( "explicit_precombat", &action, 0 );
  else
  {
    sim2gse_precombat_gcd = std::max( sim2gse_precombat_gcd, action.gcd() );
    sim2gse_precombat_cast = std::max( sim2gse_precombat_cast, action.execute_time() );
  }
}

unsigned controller_t::exchange_origin( unsigned value )
{
  const auto previous = sim2gse_origin;
  sim2gse_origin = value;
  return previous;
}

timespan_t controller_t::sim2gse_action_delay(action_t* a, bool client_clock)
{
  if (a->gcd() == 0_ms) return 0_ms;
  const auto ready = client_clock ? sim2gse_client_gcd_ready : owner_->gcd_ready;
  auto delay = std::max(0_ms, ready - owner_->sim->current_time());
  delay = std::max(delay, a->cooldown->remains());
  if (!a->usable_during_current_cast())
    delay = std::max(delay, sim2gse_precombat_cast_ready - owner_->sim->current_time());
  if (owner_->executing && owner_->executing->execute_event)
    delay = std::max(delay, owner_->executing->execute_event->remains());
  else if (owner_->channeling && owner_->channeling->get_dot())
    delay = std::max(delay, owner_->channeling->get_dot()->remains());
  return delay;
}

bool controller_t::sim2gse_queue_requirements(action_t* a)
{
  a->sim2gse_ignore_cooldown_ready = true;
  const bool ready = a->action_ready();
  a->sim2gse_ignore_cooldown_ready = false;
  return ready;
}

void controller_t::sim2gse_finish_committed()
{
  auto* committed = sim2gse_committed;
  auto committed_from = sim2gse_committed_origin;
  sim2gse_committed = nullptr;
  sim2gse_waiting_confirmation = false;
  sim2gse_candidates.clear();
  if (committed && sim2gse_tentative_gcd)
  {
    handle_event("queue_confirm", committed, committed_from);
    sim2gse_tentative_gcd = false;
    sim2gse_confirmed_tentative_gcd = true;
    sim2gse_confirmed_tentative_origin = committed_from;
    sim2gse_confirmed_tentative_action = committed;
  }
  if (committed) sim2gse_dispatch_action(committed, committed_from);
}

void controller_t::sim2gse_execute_committed()
{
  if (!sim2gse_committed) return;
  const auto native_delay = sim2gse_action_delay(sim2gse_committed, false);
  const auto execute_delay = native_delay + std::max(0_ms, owner_->rng().gauss(owner_->sim->queue_lag));
  sim2gse_queue = make_event(*owner_->sim, execute_delay + 1_ms, [this] {
    sim2gse_queue = nullptr;
    if (sim2gse_tentative_gcd && sim2gse_tentative_stable_reads < 2)
    {
      sim2gse_waiting_confirmation = true;
      return;
    }
    sim2gse_finish_committed();
  });
}

void controller_t::sim2gse_commit_pending(bool defer_execution)
{
  auto* next = sim2gse_pending;
  auto from = sim2gse_pending_origin;
  sim2gse_pending = nullptr;
  if (!next) return;
  if (!sim2gse_queue_requirements(next))
  {
    handle_event("commit_failed", next, from);
    sim2gse_candidates.clear();
    return;
  }
  sim2gse_committed = next;
  sim2gse_committed_origin = from;
  if (sim2gse_observed_gcd_states.empty())
    sim2gse_client_gcd_ready = std::max(owner_->sim->current_time(), owner_->gcd_ready) + next->gcd();
  handle_event(sim2gse_observed_gcd_states.empty() ? "queue_commit" : "queue_tentative", next, from);
  if (!defer_execution) sim2gse_execute_committed();
}

// Queue scheduling and feedback retain the existing native execution rules.
void controller_t::sim2gse_arm_queue()
{
  event_t::cancel(sim2gse_commit);
  if (!sim2gse_pending) return;
  if (!sim2gse_observed_gcd_states.empty()) return;
  const auto delay = sim2gse_action_delay(sim2gse_pending, true);
  const auto commit_lead = owner_->sim->current_time() < sim2gse_precombat_gcd ? 0_ms :
                           owner_->sim->queue_gcd_reduction;
  const auto commit_delay = std::max(0_ms, delay - commit_lead);
  sim2gse_commit = make_event(*owner_->sim, commit_delay, [this] {
    sim2gse_commit = nullptr;
    sim2gse_commit_pending();
  });
}

std::string controller_t::unavailable_reason( const std::string& signature ) const
{
  std::vector<unsigned> ids;
  for ( const auto& text : util::string_split( optional_spell_ids_, "," ) )
  {
    const auto fields = util::string_split( text, ":" );
    if ( fields.size() != 2 ) throw std::runtime_error("invalid optional spell identity");
    const int id = util::to_int( fields[0] );
    if ( id <= 0 ) throw std::runtime_error("invalid optional spell identity");
    const auto names = owner_->action_names_from_spell_id( static_cast<unsigned>( id ) );
    if ( range::find( names, fields[1] ) == names.end() )
      throw std::runtime_error("optional spell identity does not match action: " + text);
    if ( fields[1] == signature ) ids.push_back( static_cast<unsigned>( id ) );
  }
  return sim2gse::unavailable_reason( *owner_, signature, ids );
}

void controller_t::write_report( js::JsonOutput root ) const
{
  auto rows = root[ "sim2gse_skipped_commands" ];
  rows.make_array();
  for ( const auto& [step, commands] : skipped_commands_ )
    for ( const auto& [position, action, reason] : commands )
    {
      auto row = rows.add();
      row[ "step" ] = step;
      row[ "position" ] = position;
      row[ "simc_action" ] = action;
      row[ "reason" ] = reason;
    }
  if ( !observation_request_.empty() )
  {
    auto report = root[ "sim2gse_rule_observations" ];
    report.val().CopyFrom( observations_.js_, report.doc().GetAllocator() );
  }
}

void controller_t::initialize_observations()
{
  if ( observation_request_.empty() ) return;
  rapidjson::Document request;
  request.Parse( observation_request_.c_str() );
  if ( request.HasParseError() || !request.IsObject() || !request.HasMember("protocol") ||
       !request["protocol"].IsInt() || (request["protocol"].GetInt() != 1 && request["protocol"].GetInt() != 2) ||
       !request.HasMember("objects") || !request["objects"].IsObject() )
    throw std::runtime_error("invalid sim2gse rule observation request");
  observation_protocol_ = request["protocol"].GetInt();
  if ( observation_protocol_ == 2 )
  {
    const std::set<std::string> names = {"action_observations", "action_events", "state_observations",
                                        "effect_observations", "effect_events"};
    if ( !request.HasMember("collections") || !request["collections"].IsObject() ||
         request["collections"].MemberCount() != names.size() )
      throw std::runtime_error("invalid sim2gse observation collections");
    for ( auto collection = request["collections"].MemberBegin();
          collection != request["collections"].MemberEnd(); ++collection )
    {
      if ( !names.count(collection->name.GetString()) || !collection->value.IsObject() )
        throw std::runtime_error("unknown sim2gse observation collection");
      for ( auto alias = collection->value.MemberBegin(); alias != collection->value.MemberEnd(); ++alias )
      {
        if ( !request["objects"].HasMember(alias->name.GetString()) || !alias->value.IsArray() )
          throw std::runtime_error("invalid sim2gse observation collection object");
        for ( const auto& field : alias->value.GetArray() )
          if ( !field.IsString() ) throw std::runtime_error("invalid sim2gse observation field");
      }
    }
  }
  for ( auto member = request["objects"].MemberBegin(); member != request["objects"].MemberEnd(); ++member )
  {
    const auto& declaration = member->value;
    if ( !declaration.IsObject() || !declaration.HasMember("kind") || !declaration["kind"].IsString() )
      throw std::runtime_error("invalid sim2gse observation object");
    auto text = [&declaration]( const char* field ) -> std::string {
      return declaration.HasMember(field) && declaration[field].IsString() ?
             declaration[field].GetString() : "";
    };
    observation_object_t object;
    object.alias = member->name.GetString();
    object.kind = text("kind");
    object.identity = text(object.kind == "action" ? "native_action" :
                           object.kind == "target_scope" ? "value" : "native_identity");
    object.base_button = text("base_button");
    object.from_action = text("from_action");
    object.qualification = text("qualification");
    if ( observation_protocol_ == 2 )
      for ( auto collection = request["collections"].MemberBegin();
            collection != request["collections"].MemberEnd(); ++collection )
        if ( collection->value.HasMember(object.alias.c_str()) )
          for ( const auto& field : collection->value[object.alias.c_str()].GetArray() )
            object.collections[collection->name.GetString()].insert(field.GetString());
    if ( object.kind == "action" )
    {
      // Prefer the exact controlled command; replacements outside the input table
      // can still be observed, without making them independent buttons.
      for ( auto* action : owner_->action_list )
      {
        if ( action->player == owner_ && !action->background && action->name_str == object.identity &&
             ( !object.action || (action->action_list && action->action_list->name_str == "sim2gse") ) )
          object.action = action;
        if ( action->player == owner_ && !action->background && action->name_str == object.base_button &&
             ( !object.button || (action->action_list && action->action_list->name_str == "sim2gse") ) )
          object.button = action;
      }
      if ( object.base_button.empty() || object.base_button == object.identity ) object.button = object.action;
    }
    else if ( object.kind == "resource" )
      object.resource = static_cast<int>( util::parse_resource_type(object.identity) );
    else if ( object.kind == "state" || object.kind == "effect" )
    {
      object.buff = buff_t::find( owner_->buff_list, object.identity );
      object.buff_unique = object.buff && std::count_if(owner_->buff_list.begin(), owner_->buff_list.end(),
          [&object](const buff_t* buff) { return buff->name_str == object.identity; }) == 1;
    }
    if ( declaration.HasMember("components") && declaration["components"].IsArray() )
      for ( const auto& component : declaration["components"].GetArray() )
        if ( component.IsObject() && component.HasMember("native_identity") &&
             component["native_identity"].IsString() && component.HasMember("target_scope") &&
             component["target_scope"].IsString() )
          object.components.emplace_back(component["native_identity"].GetString(),
              [&request, &component]() -> std::string {
                const auto scope = request["objects"].FindMember(component["target_scope"].GetString());
                if ( scope != request["objects"].MemberEnd() && scope->value.IsObject() &&
                     scope->value.HasMember("value") && scope->value["value"].IsString() )
                  return scope->value["value"].GetString();
                return "";
              }());
    observation_objects_.push_back( std::move(object) );
  }
  for ( const auto& effect : observation_objects_ )
    if ( effect.kind == "effect" && !effect.qualification.empty() )
      for ( const auto& source : observation_objects_ )
        if ( source.kind == "action" && source.alias == effect.from_action && source.action )
        {
          auto [entry, added] = observation_qualification_sources_.emplace(effect.qualification, source.action);
          if ( !added && entry->second != source.action ) entry->second = nullptr;
        }
}

bool controller_t::observation_wants( const observation_object_t& object, const char* collection,
                                      const char* field ) const
{
  if ( observation_protocol_ == 1 ) return true;
  const auto found = object.collections.find(collection);
  return found != object.collections.end() && (!field || found->second.count(field));
}

void controller_t::start_observations()
{
  if ( observation_request_.empty() || observation_complete_ ||
       (owner_->sim->iterations != 1 && owner_->sim->current_iteration < 1) ) return;
  observations_.js_.SetObject();
  observation_event_ = 0;
  observation_active_ = true;
  js::JsonOutput root( observations_.js_, observations_.js_ );
  root["protocol"] = observation_protocol_;
  if ( observation_protocol_ == 2 )
  {
    rapidjson::Document request;
    request.Parse(observation_request_.c_str());
    root["request"].val().CopyFrom(request, observations_.js_.GetAllocator());
  }
  auto scope = root["scope"];
  scope["sample_selection"] = "first_scored_complete";
  scope["sample_id"] = owner_->sim->current_iteration;
  scope["controlled_actor_index"] = owner_->actor_index;
  scope["start_ms"] = owner_->sim->current_time().total_millis();
  scope["end_ms"].val().SetNull();
  scope["complete"] = false;
  // Some native overrides bypass the base execution counter. An absent event
  // therefore stays unknown; it is never evidence of failure.
  scope["execution_events_complete"] = false;
  scope["effect_events_complete"].val().SetObject();
  for ( const auto& object : observation_objects_ )
    if ( object.kind == "effect" && observation_wants(object, "effect_events") )
      scope["effect_events_complete"][object.alias] = false;
  for ( const auto* name : { "inputs", "action_observations", "action_events",
                            "state_observations", "effect_observations", "feedback_events", "effect_events" } )
    root[name].make_array();
  observation_buff_instance_ = 0;
  observation_buffs_active_ = true;
  for ( const auto& object : observation_objects_ )
    if ( object.kind == "effect" && object.buff && object.buff->player == owner_ &&
         object.buff->stack_behavior != buff_stack_behavior::ASYNCHRONOUS )
      observation_buffs_.emplace(object.buff, buff_observation_t{});
  for ( auto& [buff, state] : observation_buffs_ )
  {
    state.coverage = typeid(*buff) == typeid(buff_t) || buff->sim2gse_lifecycle_audited;
    if ( buff->check() > 0 )
    {
      state.instance = ++observation_buff_instance_;
      state.active = true; // Its actual application preceded this observation scope.
      write_buff_event(*buff, "observed_active", nullptr);
    }
  }
  observation_dots_active_ = true;
  observation_dot_token_ = 0;
  // One request-filtered initial read of existing native objects. Never create
  // a Dot to turn an unresolved identity into proof of absence.
  std::set<player_t*> targets;
  for ( const auto& object : observation_objects_ )
    if ( object.kind == "target_scope" )
    {
      if ( object.identity == "controlled_player" ) targets.insert(owner_);
      else if ( object.identity == "current_attack_target" && owner_->target ) targets.insert(owner_->target);
      else if ( object.identity == "all_currently_engaged_required_targets" )
        for ( auto* target : owner_->sim->target_non_sleeping_list ) targets.insert(target);
    }
  for ( const auto& object : observation_objects_ )
    if ( !object.components.empty() )
    {
      bool resolved = true;
      for ( const auto& [identity, scope] : object.components )
      {
        bool found = false;
        for ( auto* target : targets )
          if ( auto* dot = target->find_dot(identity, owner_) )
          {
            found = true;
            auto& state = observation_dots_[dot];
            if ( dot->is_ticking() && !state.active )
            {
              state.instance = ++observation_buff_instance_;
              state.active = true;
              if ( dot->end_event ) state.deadline = dot->end_event->occurs();
              write_dot_event(*dot, "observed_active");
            }
          }
        resolved = resolved && found;
      }
      observation_dot_coverage_[object.alias] = resolved;
    }
}

js::JsonOutput controller_t::observation_row( const char* collection, unsigned origin,
                                             const std::string& object )
{
  js::JsonOutput root( observations_.js_, observations_.js_ );
  auto row = root[collection].add();
  row["sample_id"] = owner_->sim->current_iteration;
  row["input_index"] = origin - 1;
  row["event_index"] = observation_event_++;
  row["time"] = owner_->sim->current_time().total_millis();
  row["source_step"] = step_for_origin(origin);
  row["input_source"] = !burst_inputs_.empty() && burst_inputs_[origin - 1] ? "burst" : "loop";
  if ( !object.empty() ) row["object"] = object;
  return row;
}

void controller_t::observe_input( unsigned origin )
{
  if ( !observation_active_ ) return;
  // The controller already limits explicit input tables to 4096. The legacy
  // periodic mode has no such table, so retain a visibly incomplete prefix.
  if ( origin > 4096 )
  {
    observation_active_ = false;
    return;
  }
  const bool burst = !burst_inputs_.empty() && burst_inputs_[origin - 1];
  const auto now = owner_->sim->current_time();
  auto occupancy = [this, now]( js::JsonOutput row ) {
    row["gcd"] = owner_->gcd_ready > now;
    row["casting"] = owner_->executing != nullptr || sim2gse_precombat_cast_ready > now;
    row["channeling"] = owner_->channeling != nullptr;
    row["queue_committed"] = sim2gse_committed != nullptr;
    row["empty"] = sim2gse_blocks[sim2gse_step].empty();
  };
  auto input = observation_row("inputs", origin);
  input["capture_stage"] = "input_before_commands";
  occupancy(input["occupancy"]);
  input["target_scopes"].val().SetObject();
  input["target_scope_sources"].val().SetObject();
  std::map<std::string, std::vector<player_t*>> scopes;
  std::map<int, player_t*> scoped_targets;
  for ( const auto& object : observation_objects_ )
    if ( object.kind == "target_scope" )
    {
      const char* source = nullptr;
      std::vector<player_t*> targets;
      if ( object.identity == "controlled_player" )
      {
        source = "controlled_actor";
        targets.push_back(owner_);
      }
      else if ( object.identity == "current_attack_target" )
      {
        source = "controlled_actor.target";
        if ( owner_->target ) targets.push_back(owner_->target);
      }
      else if ( object.identity == "all_currently_engaged_required_targets" )
      {
        // This native membership can exclude invulnerable targets. It is a
        // requirement set, not proof of a component's legal target list.
        source = "sim.target_non_sleeping_list";
        for ( auto* target : owner_->sim->target_non_sleeping_list ) targets.push_back(target);
      }
      input["target_scope_sources"][object.alias].val().SetNull();
      auto members = input["target_scopes"][object.alias];
      members.val().SetNull();
      if ( !source ) continue;
      input["target_scope_sources"][object.alias] = source;
      members.make_array();
      scopes[object.identity] = targets;
      for ( auto* target : targets )
      {
        scoped_targets[target->actor_index] = target;
        auto row = members.add();
        row["target_id"] = target->actor_index;
        row["required"] = true;
      }
    }
  for ( const auto& object : observation_objects_ )
  {
    if ( object.kind == "action" )
    {
      auto row = observation_row("action_observations", origin, object.alias);
      row["observation_kind"] = "input_snapshot";
      row["input_allowed"] = !burst;
      row["attempt"] = false;
      for ( const auto* field : { "native_qualified", "actual_form", "success", "failure_reason",
                                 "earliest_execute", "effect_completion_time", "occupancy_start",
                                 "occupancy_end", "occupancy_domains", "resource_costs",
                                 "known_native_requirements" } ) row[field].val().SetNull();
      row["known_native_requirements"].make_array();
      auto awake = row["known_native_requirements"].add();
      awake["name"] = "actor_awake";
      awake["value"] = !owner_->is_sleeping();
      auto unstunned = row["known_native_requirements"].add();
      unstunned["name"] = "actor_not_stunned";
      unstunned["value"] = owner_->buffs.stunned->check() == 0;
      row["native_requirements_complete"] = false;
      row["base_button"] = object.base_button;
      row["resource_as_of"] = owner_->last_regen.total_millis();
      auto balances = row["resource_balances"];
      if ( owner_->resource_regeneration == regen_type::DYNAMIC && owner_->last_regen != now )
        balances.val().SetNull();
      else for ( resource_e resource = RESOURCE_NONE; ++resource < RESOURCE_MAX; )
        if ( owner_->resources.max[resource] > 0 )
          balances[util::resource_type_string(resource)] = owner_->resources.current[resource];
      observe_action( row, object.action, object.button, object );
      continue;
    }
    if ( object.kind == "state" || object.kind == "resource" )
    {
      auto row = observation_row("state_observations", origin, object.alias);
      row["observation_kind"] = "input_snapshot";
      row["value"].val().SetNull();
      if ( object.identity == "literal.true" ) row["value"] = true;
      else if ( object.identity == "controlled_input.occupancy" )
      {
        row["value"].val().SetObject();
        occupancy(row["value"]);
      }
      else if ( object.identity == "current_target.health_pct" && owner_->target )
      {
        row["value"] = owner_->target->health_percentage();
        row["target_id"] = owner_->target->actor_index;
      }
      else if ( object.kind == "resource" && object.resource > RESOURCE_NONE && object.resource < RESOURCE_MAX )
      {
        row["resource_as_of"] = owner_->last_regen.total_millis();
        if ( owner_->resource_regeneration != regen_type::DYNAMIC || owner_->last_regen == now )
          row["value"] = owner_->resources.current[object.resource];
        row["maximum"] = owner_->resources.max[object.resource];
      }
      else if ( object.buff ) row["value"] = object.buff->check();
      else
      {
        const auto source = observation_qualification_sources_.find(object.alias);
        bool qualified = false;
        if ( source != observation_qualification_sources_.end() && source->second &&
             owner_->sim2gse_read_rule_effect_qualification(*source->second, object.identity, qualified) )
          row["value"] = qualified;
      }
      continue;
    }
    if ( object.kind != "effect" ) continue;
    auto effect = [this, origin, &object]( const std::string& identity, player_t* target, buff_t* buff,
                                         bool excluded = false ) {
      // Preserve the global event identity, without constructing unrequested facts.
      if ( !observation_wants(object, "effect_observations") ) { ++observation_event_; return; }
      auto row = observation_row("effect_observations", origin, object.alias);
      row["observation_kind"] = "input_snapshot";
      row["lifecycle_complete"] = false;
      row["effect_id"] = identity;
      row["component_id"] = identity;
      row["source_id"] = owner_->actor_index;
      if ( target ) row["target_id"] = target->actor_index;
      row["applicable"].val().SetNull();
      if ( excluded ) row["applicable"] = false;
      for ( const auto* field : { "active", "stacks", "remains", "instance_id" } )
        if ( observation_wants(object, "effect_observations", field) ) row[field].val().SetNull();
      if ( buff )
      {
        row["applicable"] = true;
        if ( observation_wants(object, "effect_observations", "active") ) row["active"] = buff->check() > 0;
        if ( observation_wants(object, "effect_observations", "stacks") ) row["stacks"] = buff->check();
        if ( observation_wants(object, "effect_observations", "remains") && buff->remains() != timespan_t::min() )
          row["remains"] = buff->remains().total_millis();
        if ( buff->source ) row["source_id"] = buff->source->actor_index;
        else row["source_id"].val().SetNull();
      }
      else if ( target && !excluded )
        if ( const auto* dot = target->find_dot(identity, owner_) )
        {
          if ( observation_wants(object, "effect_observations", "active") ) row["active"] = dot->is_ticking();
          if ( dot->is_ticking() ) row["applicable"] = true;
          if ( observation_wants(object, "effect_observations", "stacks") ) row["stacks"] = dot->current_stack();
          if ( observation_wants(object, "effect_observations", "remains") ) row["remains"] = dot->remains().total_millis();
        }
    };
    if ( object.components.empty() ) effect(object.identity, object.buff ? owner_ : owner_->target, object.buff);
    else for ( const auto& [identity, scope] : object.components )
      for ( const auto& [index, target] : scoped_targets )
      {
        const auto members = scopes.find(scope);
        const bool excluded = members != scopes.end() &&
            std::find(members->second.begin(), members->second.end(), target) == members->second.end();
        effect(identity, target, nullptr, excluded);
      }
  }
}

void controller_t::observe_ready( action_t* action, unsigned origin, bool ready )
{
  if ( !observation_active_ ) return;
  for ( const auto& object : observation_objects_ )
    if ( object.kind == "action" && (object.action == action || object.button == action) )
    {
      auto row = observation_row("action_events", origin, object.alias);
      row["kind"] = "qualification";
      row["capture_stage"] = "native_action_ready_result";
      row["attempt"] = true;
      row["native_qualified"] = ready;
      if ( !ready ) row["failure_reason"] = "native_action_not_ready";
      if ( observation_protocol_ == 2 )
      {
        // The actual ready caller is available without re-running an action getter.
        row["ready_action"] = action->name_str;
        if ( action->target ) row["target_id"] = action->target->actor_index;
        continue;
      }
      row["cooldown_remaining"] = action->cooldown->remains().total_millis();
      row["resource_as_of"] = owner_->last_regen.total_millis();
      auto balances = row["resource_balances"];
      if ( owner_->resource_regeneration == regen_type::DYNAMIC &&
           owner_->last_regen != owner_->sim->current_time() ) balances.val().SetNull();
      else for ( resource_e resource = RESOURCE_NONE; ++resource < RESOURCE_MAX; )
        if ( owner_->resources.max[resource] > 0 )
          balances[util::resource_type_string(resource)] = owner_->resources.current[resource];
      if ( action->target ) row["target_id"] = action->target->actor_index;
      observe_action( row, object.action, object.button, object );
    }
}

void controller_t::observe_action( js::JsonOutput row, action_t* action, action_t* button,
                                  const observation_object_t& object )
{
  if ( observation_wants(object, "action_observations", "estimated_effect_completion_time") )
    row["estimated_effect_completion_time"].val().SetNull();
  if ( observation_wants(object, "action_observations", "effect_completion_estimate") )
    row["effect_completion_estimate"].val().SetNull();
  if ( action )
  {
    row["cooldown_remaining"] = action->cooldown->remains().total_millis();
    row["charges_current"] = action->cooldown->charges > 1 ?
                              action->cooldown->current_charge : (action->cooldown->up() ? 1 : 0);
    row["charges_maximum"] = action->cooldown->charges;
    row["has_cooldown"] = action->cooldown->duration > 0_ms ||
                          action->cooldown->remains() > 0_ms || action->cooldown->charges > 1;
    if ( action->target ) row["target_id"] = action->target->actor_index;
  }
  // Class adapters reuse only their already audited native getter chains.
  // An unresolved base button must not be replaced by a cached inactive leaf.
  if ( button ) owner_->sim2gse_read_rule_action( *button, row );
  const auto& value = row.val();
  for ( const auto* field : { "gcd_ms", "cast_ms", "channel_ms", "cooldown_remaining" } )
    if ( !value.HasMember(field) || !value[field].IsNumber() ) return;
  if ( sim2gse_committed || sim2gse_pending ) return;
  const auto now = owner_->sim->current_time();
  auto earliest = now + timespan_t::from_millis(value["cooldown_remaining"].GetDouble());
  if ( value["gcd_ms"].GetDouble() > 0 ) earliest = std::max(earliest, owner_->gcd_ready);
  if ( owner_->executing )
  {
    if ( !owner_->executing->execute_event ) return;
    earliest = std::max(earliest, owner_->executing->execute_event->occurs());
  }
  if ( owner_->channeling )
  {
    const auto* channel = owner_->channeling;
    const auto* dot = channel->target ? channel->target->find_dot(channel->name_str, owner_) : nullptr;
    if ( !dot ) return;
    earliest = std::max(earliest, now + dot->remains());
  }
  earliest = std::max(earliest, sim2gse_precombat_cast_ready);
  if ( observation_wants(object, "action_observations", "timing_precision") )
    row["timing_precision"] = "current_state_estimate";
  row["earliest_execute"] = earliest.total_millis();
  row["occupancy_start"] = earliest.total_millis();
  row["occupancy_end"] = earliest.total_millis() + std::max(value["gcd_ms"].GetDouble(),
      value["cast_ms"].GetDouble() + value["channel_ms"].GetDouble());
  if ( value.HasMember("effect_completion_estimate") && value["effect_completion_estimate"].IsObject() &&
       value["effect_completion_estimate"].HasMember("effect_delay_ms") &&
       value["effect_completion_estimate"]["effect_delay_ms"].IsNumber() )
    row["estimated_effect_completion_time"] = earliest.total_millis() + value["cast_ms"].GetDouble() +
        value["effect_completion_estimate"]["effect_delay_ms"].GetDouble();
  auto domains = row["occupancy_domains"];
  domains.make_array();
  if ( value["gcd_ms"].GetDouble() > 0 ) domains.add() = "gcd";
  if ( value["cast_ms"].GetDouble() > 0 ) domains.add() = "casting";
  if ( value["channel_ms"].GetDouble() > 0 ) domains.add() = "channeling";
}

void controller_t::observe_execute( action_t& action )
{
  if ( !observation_active_ ) return;
  const auto found = observation_execution_origins_.find(&action);
  if ( found == observation_execution_origins_.end() ) return;
  const auto [origin, command] = found->second;
  if ( action.player != owner_ || !observation_counted_actions_.insert(&action).second ) return;
  for ( const auto& object : observation_objects_ )
    if ( object.kind == "action" && object.button == command &&
         (object.identity == command->name_str || object.identity == action.name_str) )
    {
      auto row = observation_row("action_events", origin, object.alias);
      row["kind"] = "execute";
      row["success"] = true;
      row["actual_form"] = action.name_str;
      if ( action.target ) row["target_id"] = action.target->actor_index;
    }
}

void controller_t::observe_replacement( action_t* from, action_t* to )
{
  if ( !observation_active_ ) return;
  const auto found = observation_execution_origins_.find(from);
  if ( found != observation_execution_origins_.end() )
    observation_execution_origins_[to] = found->second;
}

void controller_t::observe_unselected( unsigned origin )
{
  if ( !observation_active_ ) return;
  // An input with a pending commitment or deferred dispatch has not finished
  // resolving. Do not turn the absence of a success event into a negative fact.
  if ( (sim2gse_pending && sim2gse_pending_origin == origin) ||
       (sim2gse_committed && sim2gse_committed_origin == origin) ||
       std::any_of(sim2gse_deferred_dispatches.begin(), sim2gse_deferred_dispatches.end(),
                   [origin](const auto& entry) { return entry.first.first == origin; }) ) return;
  const auto& block = sim2gse_blocks[step_for_origin(origin)];
  for ( const auto& object : observation_objects_ )
    if ( object.kind == "action" && object.button &&
         std::none_of(block.begin(), block.end(), [&object](const action_t* action) {
           return action == object.action || action == object.button ||
                  action->name_str == object.identity || action->name_str == object.base_button;
         }) )
    {
      auto row = observation_row("action_events", origin, object.alias);
      row["kind"] = "outcome";
      row["outcome"] = "not_attempted";
      row["attempt"] = false;
      row["success"] = false;
      row["failure_reason"].val().SetNull();
    }
}

void controller_t::execution_end( action_t* action )
{
  observation_execution_origins_.erase(action);
  observation_counted_actions_.erase(action);
}

void controller_t::write_buff_event( buff_t& buff, const char* kind, const char* reason, action_t* consumer )
{
  const auto& state = observation_buffs_.at(&buff);
  for ( const auto& object : observation_objects_ )
    if ( object.kind == "effect" && object.buff == &buff )
    {
      if ( !observation_wants(object, "effect_events") ) { ++observation_event_; continue; }
      js::JsonOutput root( observations_.js_, observations_.js_ );
      auto row = root["effect_events"].add();
      row["object"] = object.alias;
      row["sample_id"] = owner_->sim->current_iteration;
      row["event_index"] = observation_event_++;
      row["time"] = owner_->sim->current_time().total_millis();
      row["effect_id"] = buff.name_str;
      row["instance_id"] = state.instance;
      row["target_id"] = buff.player->actor_index;
      if ( buff.source ) row["source_id"] = buff.source->actor_index;
      else row["source_id"].val().SetNull();
      row["applicable"] = true; // An actual application to this requested Buff owner.
      row["kind"] = kind;
      if ( observation_wants(object, "effect_events", "stacks") ) row["stacks"] = buff.current_stack;
      row["lifecycle_complete"] = state.complete;
      for ( const auto* field : {"start", "end", "end_reason", "scheduled_end",
                                 "source_input_index", "source_actual_action"} )
        if ( observation_wants(object, "effect_events", field) ) row[field].val().SetNull();
      if ( state.start != timespan_t::min() ) row["start"] = state.start.total_millis();
      if ( reason )
      {
        row["end"] = owner_->sim->current_time().total_millis();
        row["end_reason"] = reason;
      }
      if ( observation_wants(object, "effect_events", "scheduled_end") && buff.expiration.size() == 1 )
        row["scheduled_end"] = buff.expiration.front()->occurs().total_millis();
      if ( consumer )
      {
        row["source_actual_action"] = consumer->name_str;
        const auto context = observation_execution_origins_.find(consumer);
        if ( context != observation_execution_origins_.end() )
          row["source_input_index"] = context->second.first - 1;
      }
    }
}

void controller_t::observe_buff( buff_t& buff, const char* event, int old_stacks,
                                action_t* action, event_t* expiration )
{
  if ( !observation_buffs_active_ ) return;
  const auto found = observation_buffs_.find(&buff);
  if ( found == observation_buffs_.end() ) return;
  auto& state = found->second;
  if ( buff.expiration.size() > 1 ) state.ambiguous = true;
  const std::string kind(event);
  if ( kind == "begin" )
  {
    if ( state.scheduling ) state.ambiguous = true;
    state.scheduling = true;
    state.schedule_changes = state.changes;
    return;
  }
  if ( kind == "consume_begin" )
  {
    state.consumer = action;
    state.consume_instance = state.instance;
    return;
  }
  if ( kind == "consume_end" ) { state.consumer = nullptr; return; }
  if ( kind == "natural_begin" )
  {
    state.natural_instance = state.instance;
    state.natural_changes = state.changes;
    state.natural_event = expiration;
    state.natural_deadline = expiration->occurs();
    return;
  }
  if ( kind == "natural_check" )
  {
    state.natural = state.active && state.instance == state.natural_instance &&
        state.changes == state.natural_changes && expiration == state.natural_event &&
        expiration->occurs() == state.natural_deadline && buff.expiration.size() == 1 &&
        buff.expiration.front() == expiration;
    if ( !state.natural ) state.ambiguous = true;
    return;
  }
  if ( kind == "natural_end" ) { state.natural = false; return; }
  if ( kind == "cancel_schedule" ) { state.scheduling = false; return; }
  if ( kind == "stack" )
  {
    if ( old_stacks == buff.current_stack ) return;
    ++state.changes;
    if ( state.scheduling && (buff.current_stack < old_stacks || state.changes > state.schedule_changes + 1) )
      state.ambiguous = true;
    if ( old_stacks == 0 && buff.current_stack > 0 )
    {
      state.instance = ++observation_buff_instance_;
      state.start = owner_->sim->current_time();
      state.active = true;
      state.complete = !state.ambiguous &&
          (typeid(buff) == typeid(buff_t) || buff.sim2gse_lifecycle_audited);
      write_buff_event(buff, "apply", nullptr);
      return;
    }
    if ( !state.active )
    {
      if ( buff.current_stack < old_stacks ) state.consumer = nullptr;
      return;
    }
    if ( state.ambiguous ) state.complete = false;
    action_t* consumer = nullptr;
    if ( buff.current_stack < old_stacks )
    {
      if ( state.consume_instance == state.instance ) consumer = state.consumer;
      state.consumer = nullptr; // Take the cause before any native callback can re-enter.
      if ( !consumer && !state.natural ) state.complete = false;
    }
    const bool ended = buff.current_stack == 0;
    const char* reason = !ended ? nullptr : consumer ? "consumed" : state.natural ? "expired" : "unknown";
    write_buff_event(buff, consumer ? "consume" : ended ? "expire" : "stack_change", reason, consumer);
    if ( ended ) state.active = false;
    state.natural = false;
    return;
  }
  if ( kind == "start" || kind == "refresh" )
  {
    if ( state.changes > state.schedule_changes + 1 ) state.ambiguous = true;
    state.scheduling = false;
  }
  if ( state.active )
  {
    if ( state.ambiguous ) state.complete = false;
    write_buff_event(buff, event, nullptr);
  }
}

void controller_t::write_dot_event( dot_t& dot, const char* kind, const char* reason )
{
  const auto& state = observation_dots_.at(&dot);
  for ( const auto& object : observation_objects_ )
    for ( const auto& [identity, scope] : object.components )
      if ( identity == dot.name_str && dot.source == owner_ )
      {
        if ( !observation_wants(object, "effect_events") ) { ++observation_event_; continue; }
        js::JsonOutput root(observations_.js_, observations_.js_);
        auto row = root["effect_events"].add();
        row["object"] = object.alias;
        row["sample_id"] = owner_->sim->current_iteration;
        row["event_index"] = observation_event_++;
        row["time"] = owner_->sim->current_time().total_millis();
        row["effect_id"] = dot.name_str;
        row["component_id"] = identity;
        row["instance_id"] = state.instance;
        row["target_id"] = dot.target->actor_index;
        row["source_id"] = dot.source->actor_index;
        row["applicable"] = true; // Actual instance, not potential target qualification.
        row["kind"] = kind;
        if ( observation_wants(object, "effect_events", "stacks") ) row["stacks"] = dot.current_stack();
        row["lifecycle_complete"] = state.complete;
        for ( const auto* field : {"start", "end", "end_reason", "scheduled_end",
                                   "source_input_index", "source_actual_action"} )
          if ( observation_wants(object, "effect_events", field) ) row[field].val().SetNull();
        if ( state.start != timespan_t::min() ) row["start"] = state.start.total_millis();
        if ( observation_wants(object, "effect_events", "scheduled_end") && state.deadline != timespan_t::min() )
          row["scheduled_end"] = state.deadline.total_millis();
        if ( reason )
        {
          row["end"] = owner_->sim->current_time().total_millis();
          row["end_reason"] = reason;
        }
      }
}

unsigned controller_t::observe_dot( dot_t& dot, const char* event, unsigned token, event_t* expiration )
{
  if ( !observation_dots_active_ || dot.source != owner_ ) return 0;
  bool requested = false;
  for ( const auto& object : observation_objects_ )
    for ( const auto& [identity, scope] : object.components )
      if ( identity == dot.name_str )
      {
        requested = true;
        if ( std::string(event) == "unsupported" ) observation_dot_coverage_[object.alias] = false;
      }
  if ( !requested ) return 0;
  auto& state = observation_dots_[&dot];
  const std::string kind(event);
  if ( kind == "unsupported" ) { state.complete = false; ++state.changes; return 0; }
  if ( kind == "natural_begin" )
  {
    state.natural_instance = state.instance;
    state.natural_changes = state.changes;
    state.natural_event = expiration;
    state.natural_deadline = expiration->occurs();
    state.token = ++observation_dot_token_;
    state.candidate = 0;
    return 0;
  }
  auto unchanged = [&]() {
    return state.active && state.instance == state.natural_instance &&
        state.changes == state.natural_changes && dot.end_event == nullptr &&
        owner_->sim->current_time() == state.natural_deadline;
  };
  if ( kind == "natural_prepare" )
  {
    if ( expiration == state.natural_event && unchanged() ) state.candidate = state.token;
    else if ( state.active ) state.complete = false;
    return 0;
  }
  if ( kind == "last_tick_begin" )
  {
    const auto candidate = state.candidate;
    state.candidate = 0; // Native callbacks cannot borrow the outer final-reset cause.
    return candidate;
  }
  if ( kind == "last_tick_end" )
  {
    state.natural = token && token == state.token && unchanged();
    if ( token && !state.natural ) state.complete = false;
    return 0;
  }
  if ( kind == "natural_end" ) { state.candidate = state.token = 0; state.natural = false; return 0; }
  if ( kind == "cancel" ) { state.candidate = 0; state.natural = false; return 0; }
  if ( kind == "reset_begin" )
  {
    if ( dot.end_event ) state.deadline = dot.end_event->occurs();
    if ( dot.is_ticking() && !state.active )
    {
      state.instance = ++observation_buff_instance_;
      state.active = true;
      state.complete = false;
      write_dot_event(dot, "observed_active");
      for ( const auto& object : observation_objects_ )
        for ( const auto& [identity, scope] : object.components )
          if ( identity == dot.name_str ) observation_dot_coverage_[object.alias] = false;
    }
    return 0;
  }
  if ( kind == "reset" )
  {
    if ( state.active )
    {
      write_dot_event(dot, "end", state.natural ? "expired" : "removed");
      state.active = false;
      ++state.changes;
    }
    state.natural = false;
    return 0;
  }
  if ( kind == "apply" )
  {
    state.instance = ++observation_buff_instance_;
    state.start = owner_->sim->current_time();
    state.active = true;
    state.complete = true;
  }
  else if ( !state.active )
  {
    state.instance = ++observation_buff_instance_;
    state.start = timespan_t::min();
    state.active = true;
    state.complete = false;
  }
  ++state.changes;
  if ( dot.end_event ) state.deadline = dot.end_event->occurs();
  write_dot_event(dot, event);
  return 0;
}

void controller_t::finish_buff_observations()
{
  if ( observation_dots_active_ )
  {
    for ( auto& [dot, state] : observation_dots_ )
    {
      if ( state.active != dot->is_ticking() )
        for ( const auto& object : observation_objects_ )
          for ( const auto& [identity, scope] : object.components )
            if ( identity == dot->name_str ) observation_dot_coverage_[object.alias] = false;
      if ( state.active )
      {
        if ( !dot->is_ticking() ) state.complete = false;
        write_dot_event(*dot, dot->is_ticking() ? "end" : "observation_gap",
                        dot->is_ticking() ? "simulation_end" : nullptr);
        state.active = false;
      }
    }
    observation_dots_active_ = false;
  }
  if ( !observation_buffs_active_ ) return;
  for ( auto& [buff, state] : observation_buffs_ )
  {
    if ( state.ambiguous || state.scheduling || state.active != (buff->check() > 0) ) state.coverage = false;
    if ( state.active )
    {
      if ( buff->check() > 0 ) write_buff_event(*buff, "end", "simulation_end");
      else
      {
        state.complete = false;
        write_buff_event(*buff, "observation_gap", nullptr);
      }
      state.active = false;
    }
  }
  observation_buffs_active_ = false;
}

void controller_t::finish_observations()
{
  if ( !observation_active_ ) return;
  js::JsonOutput root( observations_.js_, observations_.js_ );
  root["scope"]["end_ms"] = owner_->sim->current_time().total_millis();
  root["scope"]["complete"] = true;
  for ( const auto& object : observation_objects_ )
    if ( object.kind == "effect" && observation_wants(object, "effect_events") )
    {
      const auto state = observation_buffs_.find(object.buff);
      root["scope"]["effect_events_complete"][object.alias] = object.buff_unique &&
          !observation_buffs_active_ && state != observation_buffs_.end() && state->second.coverage;
      if ( !object.components.empty() )
        root["scope"]["effect_events_complete"][object.alias] = !observation_dots_active_ &&
            observation_dot_coverage_[object.alias];
    }
  observation_complete_ = true;
  observation_active_ = false;
}

void controller_t::sim2gse_init()
{
  if ( sim2gse_steps.empty() ) return;
  initialize_times();
  if ( owner_->is_pet() || owner_->is_enemy() || owner_->sim->threads != 1 )
    throw std::runtime_error("sim2gse requires one-thread player");
  if ( sim2gse_window < 0_ms || sim2gse_window > 400_ms )
    throw std::runtime_error("sim2gse prototype window must be 0..400ms");
  auto* list = owner_->find_action_priority_list("sim2gse");
  if ( !list || list->action_list.empty() )
    throw std::runtime_error("sim2gse prototype requires actions.sim2gse");
  std::vector<action_t*> resolved_actions;
  std::vector<std::string> skipped_reasons;
  for ( const auto& entry : list->action_list )
  {
    const auto reason = unavailable_reason( entry.action_ );
    const auto found = range::find_if( list->foreground_action_list, [&entry]( const action_t* action ) {
      return action->signature_str == entry.action_;
    } );
    if ( reason.empty() && found == list->foreground_action_list.end() )
      throw std::runtime_error("sim2gse action unavailable without evidence: " + entry.action_);
    resolved_actions.push_back( reason.empty() ? *found : nullptr );
    skipped_reasons.push_back( reason );
  }
  if (!sim2gse_castsequences.empty())
  {
    for (auto definition : util::string_split(sim2gse_castsequences, "/"))
    {
      auto fields = util::string_split(definition, ":");
      if ((fields.size() < 2 || fields.size() > 4) || fields[0].empty() ||
          fields[0].find_first_not_of("0123456789") != std::string::npos)
        throw std::runtime_error("invalid sim2gse castsequence definition");
      const auto step = std::stoul(fields[0]);
      if (sim2gse_castsequence_members.count(step))
        throw std::runtime_error("duplicate sim2gse castsequence step");
      if (fields.size() >= 3)
      {
        if (fields[2].empty() || fields[2].find_first_not_of("0123456789") != std::string::npos)
          throw std::runtime_error("invalid sim2gse castsequence timeout");
        const auto timeout = std::stoull(fields[2]);
        if (timeout > 2147483647000ULL || (timeout == 0 && fields.size() == 3))
          throw std::runtime_error("sim2gse castsequence timeout out of range");
        if (timeout > 0)
          sim2gse_castsequence_timeouts.emplace(step, timespan_t::from_millis(timeout));
      }
      if (fields.size() == 4)
      {
        if (fields[3].empty() || fields[3].find_first_not_of("0123456789") != std::string::npos)
          throw std::runtime_error("invalid sim2gse castsequence reset flags");
        const auto flags = std::stoul(fields[3]);
        if (flags == 0 || flags > 31)
          throw std::runtime_error("sim2gse castsequence reset flags out of range");
        sim2gse_castsequence_reset_flags.emplace(step, flags);
      }
      std::vector<action_t*> members;
      for (auto index : util::string_split(fields[1], ","))
      {
        if (index.empty() || index.find_first_not_of("0123456789") != std::string::npos)
          throw std::runtime_error("invalid sim2gse castsequence member");
        const auto n = std::stoul(index);
        if (n == 0 || n > resolved_actions.size())
          throw std::runtime_error("sim2gse castsequence member out of range");
        auto* action = resolved_actions[n - 1];
        if ( !action ) throw std::runtime_error("unavailable castsequence member");
        if (action->background || action->type == ACTION_VARIABLE || action->name_str == "use_items" ||
            action->name_str == "call_action_list" || action->name_str == "run_action_list")
          throw std::runtime_error("unsupported sim2gse castsequence action: " + action->name_str);
        members.push_back(action);
      }
      if (members.size() < 2 || members.size() > 32)
        throw std::runtime_error("sim2gse castsequence requires 2..32 members");
      sim2gse_castsequence_members.emplace(step, std::move(members));
      sim2gse_castsequence_positions.emplace(step, 0);
    }
  }
  // Python/GSE bound source nodes separately. These are expanded clicks, with an
  // independent 4096-click limit for each ordinary/burst macro, not their sum.
  const auto blocks = util::string_split(sim2gse_steps, "/");
  if ( blocks.empty() || ( input_sources_text_.empty() ? blocks.size() > 4096 :
       ( !burst_offset_ || burst_offset_ > 4096 || burst_offset_ >= blocks.size() ||
         blocks.size() - burst_offset_ > 4096 ) ) )
    throw std::runtime_error("invalid sim2gse sequence length: each source requires 1..4096 clicks");
  for ( auto block : blocks )
  {
    const auto block_index = static_cast<unsigned>(sim2gse_blocks.size());
    if (block == "0")
    {
      fmt::print("S2GBLOCK\t{}\t-1\t-\n", sim2gse_blocks.size());
      sim2gse_blocks.emplace_back();
      continue;
    }
    std::vector<action_t*> actions;
    std::set<unsigned> gcd_buttons;
    for ( auto index : util::string_split(block, "+") )
    {
      if ( index.empty() || index.find_first_not_of("0123456789") != std::string::npos )
        throw std::runtime_error("invalid sim2gse action index");
      auto n = std::stoul(index);
      if ( n == 0 || n > resolved_actions.size() )
        throw std::runtime_error("sim2gse action index out of range");
      auto* a = resolved_actions[n - 1];
      if ( !a ) continue;
      if ( a->background || !a->option.if_expr_str.empty() || !a->option.target_if_str.empty() ||
           a->type == ACTION_VARIABLE || a->name_str == "use_items" ||
           a->name_str == "call_action_list" || a->name_str == "run_action_list" )
        throw std::runtime_error("unsupported sim2gse prototype action: " + a->name_str);
      const auto button = owner_->sim2gse_base_spell_id(a->data().id());
      sim2gse_button_ids[a] = button;
      if (a->gcd() > 0_ms) gcd_buttons.insert(button);
      if ( gcd_buttons.size() > 1 && !sim2gse_castsequence_members.count(block_index) )
        throw std::runtime_error("prototype supports at most one GCD action per block");
      actions.push_back(a);
    }
    const auto castsequence = sim2gse_castsequence_members.find(block_index);
    if (castsequence != sim2gse_castsequence_members.end() && actions != castsequence->second)
      throw std::runtime_error("sim2gse castsequence members do not match its block");
    unsigned position = 0;
    for ( const auto& index : util::string_split( block, "+" ) )
    {
      const auto n = std::stoul( index ) - 1;
      fmt::print("S2GBLOCK\t{}\t{}\t{}\n", sim2gse_blocks.size(), position,
                 list->action_list[n].action_);
      if ( !skipped_reasons[n].empty() )
      {
        fmt::print("S2GSKIP\t{}\t{}\t{}\t{}\n", sim2gse_blocks.size(), position,
                   list->action_list[n].action_, skipped_reasons[n]);
        skipped_commands_[static_cast<unsigned>(sim2gse_blocks.size())].emplace_back(
          position, list->action_list[n].action_, skipped_reasons[n]);
      }
      ++position;
    }
    sim2gse_blocks.push_back(actions);
  }
  initialize_sources();
  for (const auto& [step, members] : sim2gse_castsequence_members)
    if (step >= sim2gse_blocks.size())
      throw std::runtime_error("sim2gse castsequence step out of range");
  for (auto value : util::string_split(sim2gse_castsequence_events, "/"))
  {
    if (value.empty()) continue;
    const auto fields = util::string_split(value, ",");
    if (fields.size() != 2 || fields[0].empty() ||
        fields[0].find_first_not_of("0123456789") != std::string::npos)
      throw std::runtime_error("invalid sim2gse castsequence event");
    const auto at = timespan_t::from_millis(std::stoul(fields[0]));
    if (at >= owner_->sim->max_time)
      throw std::runtime_error("sim2gse castsequence event exceeds combat");
    const unsigned flag = fields[1] == "target" ? 1 : fields[1] == "combat" ? 2 :
                          fields[1] == "shift" ? 4 : fields[1] == "ctrl" ? 8 :
                          fields[1] == "alt" ? 16 : fields[1] == "death" ? 32 : 0;
    if (!flag)
      throw std::runtime_error("unknown sim2gse castsequence event");
    sim2gse_castsequence_reset_events.emplace_back(at, flag);
    if (flag & (4 | 8 | 16)) sim2gse_castsequence_modifiers[at] |= flag;
  }
  initialize_observations();
}

void controller_t::sim2gse_reset_castsequence(unsigned step)
{
  ++sim2gse_castsequence_generations[step];
  sim2gse_castsequence_positions[step] = 0;
  sim2gse_castsequence_pending_origins.erase(step);
  sim2gse_castsequence_last_use.erase(step);
}

void controller_t::sim2gse_castsequence_update()
{
  std::vector<unsigned> expired;
  for (const auto& [step, used_at] : sim2gse_castsequence_last_use)
    if (owner_->sim->current_time() - used_at >= sim2gse_castsequence_timeouts[step])
      expired.push_back(step);
  for (auto step : expired) sim2gse_reset_castsequence(step);
  if (owner_->sim->current_time() + 1_s < owner_->sim->max_time)
    make_event(*owner_->sim, 1_s, [this] { sim2gse_castsequence_update(); });
}

void controller_t::handle_event(const char* event, action_t* a, unsigned origin)
{
  const bool native_execute = std::string(event) == "native_execute";
  const bool native_interrupt = std::string(event) == "native_interrupt";
  const auto issued = issued_actions_.find( { origin, a } );
  action_t* command = issued == issued_actions_.end() ? nullptr : issued->second;
  if ( observation_active_ && native_execute && command )
    observation_execution_origins_[a] = {origin, command};
  if ( !command && !native_execute && !native_interrupt && origin && a &&
       std::find(sim2gse_blocks[step_for_origin(origin)].begin(),
                 sim2gse_blocks[step_for_origin(origin)].end(), a) !=
       sim2gse_blocks[step_for_origin(origin)].end() )
    command = a; // Controller failures may happen before native dispatch.
  bool sequence_pending_success = false;
  int sequence_step = -1;
  int sequence_member = -1;
  if (origin)
  {
    const auto step = step_for_origin(origin);
    const auto sequence = sim2gse_castsequence_members.find(step);
    if (sequence != sim2gse_castsequence_members.end())
    {
      sequence_step = static_cast<int>(step);
      const auto original = sim2gse_castsequence_origin_members.find(origin);
      sequence_member = static_cast<int>(original == sim2gse_castsequence_origin_members.end() ?
                                         sim2gse_castsequence_positions[step] : original->second);
      auto pending = sim2gse_castsequence_pending_origins.find(step);
      sequence_pending_success = native_execute && command && pending != sim2gse_castsequence_pending_origins.end() &&
                                 pending->second == origin;
      if (pending != sim2gse_castsequence_pending_origins.end() && pending->second == origin &&
          (((native_execute || native_interrupt || std::string(event) == "dispatch_failed") && command) ||
           std::string(event) == "observed_failed" || std::string(event) == "queue_rollback" ||
           std::string(event) == "replace"))
        sim2gse_castsequence_pending_origins.erase(pending);
      if (std::string(event) == "queue_restore" && command == sequence->second[sequence_member] &&
          sim2gse_castsequence_origin_generations[origin] == sim2gse_castsequence_generations[step])
        sim2gse_castsequence_pending_origins[step] = origin;
    }
  }
  if (native_execute && command)
  {
    sim2gse_executed_actions.emplace(origin, command);
    const auto step = step_for_origin(origin);
    const auto sequence = sim2gse_castsequence_members.find(step);
    if (sequence != sim2gse_castsequence_members.end() && sequence_pending_success)
    {
      auto& position = sim2gse_castsequence_positions[step];
      if (position >= sequence->second.size() || sequence->second[position] != command)
        throw std::runtime_error("sim2gse castsequence success does not match current member");
      position = (position + 1) % sequence->second.size();
    }
  }
  if ( observation_active_ && origin && (!(native_execute || native_interrupt) || command) )
  {
    static const std::set<std::string> feedback_events = {
      "input", "not_ready", "outside_window", "queue", "dispatch", "busy", "dispatch_failed",
      "native_execute", "queue_locked", "queue_commit", "queue_confirm", "queue_tentative",
      "native_interrupt", "observed_failed", "commit_failed", "queue_rollback", "late_negative_feedback"
    };
    if ( feedback_events.count(event) )
    {
      js::JsonOutput root( observations_.js_, observations_.js_ );
      auto row = root["feedback_events"].add();
      row["event_index"] = observation_event_++;
      row["event"] = event;
      row["ms"] = owner_->sim->current_time().total_millis();
      row["origin"] = origin;
      row["step"] = step_for_origin(origin);
      row["action"] = a ? a->name_str : "-";
      row["signature"] = command ? command->signature_str : a ? a->signature_str : "-";
      row["battle"] = owner_->sim->current_iteration;
      row["rp"] = owner_->resources.current[owner_->primary_resource()];
      row["source"] = !burst_inputs_.empty() && burst_inputs_[origin - 1] ? "burst" : "loop";
      row["source_origin"] = source_origins_.empty() ? origin : source_origins_[origin - 1];
      row["sequence_step"] = sequence_step;
      row["sequence_member"] = sequence_member;
    }
  }
  write_trace( event, a, origin, sequence_step, sequence_member, command );
}

void controller_t::write_trace( const char* event, action_t* a, unsigned origin,
                                int sequence_step, int sequence_member, action_t* command ) const
{
  if ( !sim2gse_trace ) return;
  if ( (std::string(event) == "native_execute" || std::string(event) == "native_interrupt") && !command )
    event = "native_derived";
  const auto source = input_steps_.empty() ? std::string() : fmt::format("\t{}\t{}",
      origin ? (burst_inputs_.at(origin - 1) ? "burst" : "loop") : "-",
      origin ? source_origins_.at(origin - 1) : 0);
  owner_->sim->out_log.print("S2GSE\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}{}", owner_->sim->current_time().total_millis(),
      event, origin, origin ? static_cast<int>(step_for_origin(origin)) : -1, a ? a->name_str : "-", owner_->gcd_ready.total_millis(),
      owner_->resources.current[owner_->primary_resource()], owner_->health_percentage(), a ? a->cooldown->remains().total_millis() : 0,
      owner_->sim->current_iteration, command ? command->signature_str : a ? a->signature_str : "-", a ? a->execute_time().total_millis() : 0,
      sequence_step, sequence_member, source);
}

void controller_t::sim2gse_dispatch_action(action_t* a, unsigned origin)
{
  if ( owner_->resource_regeneration == regen_type::DYNAMIC ) owner_->do_dynamic_regen();
  const bool casting = owner_->executing || owner_->channeling;
  const bool precombat_casting = sim2gse_precombat_cast_ready > owner_->sim->current_time();
  if ( owner_->is_sleeping() || ((casting || precombat_casting) && !a->usable_during_current_cast()) ||
       owner_->buffs.stunned->check() || !a->action_ready() ||
       (a->gcd() > 0_ms && owner_->gcd_ready > owner_->sim->current_time()) ||
       !a->cooldown->up() )
  {
    handle_event("dispatch_failed", a, origin);
    return;
  }
  const auto [issued, inserted] = issued_actions_.emplace(std::make_pair(origin, a), a);
  if (!inserted && issued->second != a)
    throw std::runtime_error("sim2gse dispatch conflicts with native replacement identity");
  handle_event("dispatch", a, origin);
  sim2gse_origin = origin;
  if (casting)
    a->queue_execute(execute_type::CAST_WHILE_CASTING);
  else if ( a->gcd() == 0_ms && a->execute_time() == 0_ms && !a->channeled )
    a->queue_execute(execute_type::OFF_GCD);
  else
  {
    sim2gse_dispatch = a;
    owner_->execute_action(); // Keep native foreground scheduling, accounting and stats.
  }
  sim2gse_origin = 0;
}

void controller_t::sim2gse_tick()
{
  if ( owner_->is_sleeping() || owner_->sim->event_mgr.canceled ) return;
  const unsigned origin = ++input_;
  if (!input_steps_.empty()) sim2gse_step = step_for_origin(origin);
  handle_event("input", nullptr, origin);
  if ( origin == 1 && sim2gse_blocks[sim2gse_step].empty() )
  {
    if ( sim2gse_precombat_gcd > 0_ms )
    {
      owner_->gcd_ready = std::max(owner_->gcd_ready, owner_->sim->current_time() + sim2gse_precombat_gcd);
      sim2gse_client_gcd_ready = owner_->gcd_ready;
      handle_event("precombat_gcd", nullptr, origin);
    }
    if ( sim2gse_precombat_cast > 0_ms )
    {
      sim2gse_precombat_cast_ready = owner_->sim->current_time() + sim2gse_precombat_cast;
      handle_event("precombat_cast", nullptr, origin);
    }
  }
  if (!sim2gse_observed_gcd_states.empty())
  {
    const auto& observed = sim2gse_observed_gcd_states[origin - 1];
    if (observed.second != 0_ms)
    {
      const auto previous_start = sim2gse_last_observed_gcd_start;
      const auto previous_duration = sim2gse_last_observed_gcd_duration;
      // A duration correction does not start or undo a GCD generation.
      const bool changed = sim2gse_observed_gcd_initialized && observed.first != previous_start;
      if (sim2gse_confirmed_tentative_gcd && changed)
      {
        if (observed.first == sim2gse_tentative_old_gcd_start &&
            sim2gse_executed_actions.count({sim2gse_confirmed_tentative_origin,
                                            sim2gse_confirmed_tentative_action}))
          handle_event("late_negative_feedback", nullptr, origin);
        sim2gse_confirmed_tentative_gcd = false;
        sim2gse_confirmed_tentative_origin = 0;
        sim2gse_confirmed_tentative_action = nullptr;
      }
      if (sim2gse_tentative_gcd && changed)
      {
        if (sim2gse_committed)
          handle_event("queue_rollback", sim2gse_committed, sim2gse_committed_origin);
        event_t::cancel(sim2gse_queue);
        sim2gse_committed = nullptr;
        sim2gse_tentative_gcd = false;
        sim2gse_tentative_stable_reads = 0;
        sim2gse_waiting_confirmation = false;
        sim2gse_candidates.clear();
      }
      else if (sim2gse_tentative_gcd &&
               observed.first == sim2gse_tentative_gcd_start &&
               ++sim2gse_tentative_stable_reads == 2 && sim2gse_waiting_confirmation)
        sim2gse_finish_committed();
      sim2gse_client_gcd_ready = observed.first + observed.second;
      if (changed && !sim2gse_tentative_gcd && sim2gse_pending)
      {
        sim2gse_commit_pending(true);
        if (sim2gse_committed)
        {
          sim2gse_tentative_gcd = true;
          sim2gse_tentative_gcd_start = observed.first;
          sim2gse_tentative_gcd_duration = observed.second;
          sim2gse_tentative_stable_reads = 0;
          sim2gse_waiting_confirmation = false;
          sim2gse_tentative_old_gcd_start = previous_start;
          sim2gse_tentative_old_gcd_duration = previous_duration;
          sim2gse_execute_committed();
        }
      }
      sim2gse_observed_gcd_initialized = true;
      sim2gse_last_observed_gcd_start = observed.first;
      sim2gse_last_observed_gcd_duration = observed.second;
    }
  }
  bool input_observed = false;
  std::set<unsigned> selected_buttons;
  const auto castsequence = sim2gse_castsequence_members.find(sim2gse_step);
  action_t* castsequence_member = nullptr;
  bool castsequence_attempted = false;
  if (castsequence != sim2gse_castsequence_members.end() && !sim2gse_castsequence_clock_started)
  {
    sim2gse_castsequence_clock_started = true;
    make_event(*owner_->sim, 1_s, [this] { sim2gse_castsequence_update(); });
  }
  const bool castsequence_waiting = castsequence != sim2gse_castsequence_members.end() &&
                                    sim2gse_castsequence_pending_origins.count(sim2gse_step);
  if (castsequence != sim2gse_castsequence_members.end() && !castsequence_waiting &&
      (sim2gse_castsequence_reset_flags[sim2gse_step] &
       sim2gse_castsequence_modifiers[owner_->sim->current_time()]))
    sim2gse_reset_castsequence(sim2gse_step);
  if (castsequence != sim2gse_castsequence_members.end())
    castsequence_member = castsequence->second[sim2gse_castsequence_positions[sim2gse_step]];
  if (castsequence != sim2gse_castsequence_members.end() && !castsequence_waiting)
  {
    sim2gse_castsequence_origin_members[origin] = sim2gse_castsequence_positions[sim2gse_step];
    sim2gse_castsequence_origin_generations[origin] = sim2gse_castsequence_generations[sim2gse_step];
  }
  if (castsequence != sim2gse_castsequence_members.end() && !castsequence_waiting &&
      sim2gse_castsequence_timeouts.count(sim2gse_step))
    sim2gse_castsequence_last_use[sim2gse_step] = owner_->sim->current_time();
  if (castsequence_waiting)
    handle_event("castsequence_pending", castsequence_member, origin);
  for ( auto* a : sim2gse_blocks[sim2gse_step] )
  {
    if (castsequence_waiting) continue;
    if (castsequence_member && (a != castsequence_member || castsequence_attempted)) continue;
    if (castsequence_member) castsequence_attempted = true;
    const auto button = sim2gse_button_ids[a];
    if (button && selected_buttons.count(button)) continue;
    if (!sim2gse_observed_failed_actions.empty() &&
        sim2gse_observed_failed_actions[origin - 1] == a->name_str)
    {
      handle_event("observed_failed", a, origin);
      continue;
    }
    if ( owner_->resource_regeneration == regen_type::DYNAMIC ) owner_->do_dynamic_regen();
    if ( !input_observed )
    {
      observe_input( origin );
      input_observed = true;
    }
    if ( owner_->buffs.stunned->check() )
    {
      handle_event("busy", a, origin);
      continue;
    }
    if ( a->gcd() > 0_ms && sim2gse_committed )
    {
      handle_event("queue_locked", a, origin);
      continue;
    }
    const bool ready_now = a->action_ready();
    observe_ready( a, origin, ready_now );
    const bool trust_failure_feedback = a->gcd() > 0_ms && !sim2gse_observed_failed_actions.empty();
    if (!ready_now && !trust_failure_feedback &&
        (a->cooldown->remains() <= 0_ms || !sim2gse_queue_requirements(a)))
    {
      handle_event("not_ready", a, origin);
      continue;
    }
    const auto delay = sim2gse_action_delay(a, true);
    if ( delay > sim2gse_window )
    {
      handle_event("outside_window", a, origin);
      continue;
    }
    const bool wait_for_gcd_feedback = a->gcd() > 0_ms && !sim2gse_observed_gcd_states.empty();
    if ( delay > 0_ms || wait_for_gcd_feedback )
    {
      if ( sim2gse_pending ) handle_event("replace", sim2gse_pending, sim2gse_pending_origin);
      event_t::cancel(sim2gse_queue);
      sim2gse_pending = a;
      sim2gse_pending_origin = origin;
      if (castsequence_member) sim2gse_castsequence_pending_origins[sim2gse_step] = origin;
      if (a->gcd() > 0_ms && sim2gse_timed_feedback)
        sim2gse_candidates.emplace_back(a, origin);
      else
        sim2gse_candidates.clear();
      handle_event("queue", a, origin);
      sim2gse_arm_queue();
    }
    else
    {
      if (castsequence_member) sim2gse_castsequence_pending_origins[sim2gse_step] = origin;
      if ( a->gcd() > 0_ms )
      {
        event_t::cancel(sim2gse_commit);
        event_t::cancel(sim2gse_queue);
        sim2gse_pending = nullptr;
        sim2gse_candidates.clear();
      }
      if ( a->gcd() > 0_ms )
        sim2gse_client_gcd_ready = owner_->sim->current_time() + a->gcd();
      if (a->gcd() == 0_ms && a->name_str != "auto_attack" && sim2gse_timed_feedback)
      {
        auto* deferred = make_event(*owner_->sim, 2_ms, [this, origin, a] {
          const auto found = sim2gse_deferred_dispatches.find({origin, a});
          if (found == sim2gse_deferred_dispatches.end()) return;
          sim2gse_deferred_dispatches.erase(found);
          sim2gse_dispatch_action(a, origin);
        });
        sim2gse_deferred_dispatches.emplace(std::make_pair(origin, a), deferred);
        handle_event("dispatch_deferred", a, origin);
      }
      else
        sim2gse_dispatch_action(a, origin);
    }
    if (button) selected_buttons.insert(button);
  }
  if ( !input_observed ) observe_input( origin );
  observe_unselected( origin );
  sim2gse_step = (sim2gse_step + 1) % sim2gse_blocks.size();
  schedule_next();
}

}
