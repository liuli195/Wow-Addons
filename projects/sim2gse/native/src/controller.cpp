#include "controller.hpp"
#include "simulationcraft.hpp"

namespace sim2gse
{
void controller_t::register_options( player_t& owner )
{
  owner_ = &owner;
  owner.add_option( opt_string("sim2gse_steps", sim2gse_steps) );
  owner.add_option( opt_string("sim2gse_castsequences", sim2gse_castsequences) );
  owner.add_option( opt_string("sim2gse_castsequence_events", sim2gse_castsequence_events) );
  owner.add_option( opt_string("sim2gse_times", sim2gse_times) );
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
  sim2gse_deferred_dispatches.clear();
  sim2gse_commit = sim2gse_queue = nullptr;
}

void controller_t::start( player_t& owner )
{
  owner_ = &owner;
  if ( !enabled() ) return;

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

void controller_t::sim2gse_init()
{
  if ( sim2gse_steps.empty() ) return;
  initialize_times();
  if ( owner_->is_pet() || owner_->is_enemy() || owner_->sim->threads != 1 )
    throw std::runtime_error("sim2gse requires one-thread player");
  if ( sim2gse_window < 0_ms || sim2gse_window > 400_ms )
    throw std::runtime_error("sim2gse prototype window must be 0..400ms");
  auto* list = owner_->find_action_priority_list("sim2gse");
  if ( !list || list->foreground_action_list.empty() )
    throw std::runtime_error("sim2gse prototype requires actions.sim2gse");
  if (list->foreground_action_list.size() != list->action_list.size())
    throw std::runtime_error("sim2gse action removed by native initialization");
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
        if (n == 0 || n > list->foreground_action_list.size())
          throw std::runtime_error("sim2gse castsequence member out of range");
        auto* action = list->foreground_action_list[n - 1];
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
  for ( auto block : util::string_split(sim2gse_steps, "/") )
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
      if ( n == 0 || n > list->foreground_action_list.size() )
        throw std::runtime_error("sim2gse action index out of range");
      auto* a = list->foreground_action_list[n - 1];
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
    if ( actions.empty() ) throw std::runtime_error("empty sim2gse block");
    const auto castsequence = sim2gse_castsequence_members.find(block_index);
    if (castsequence != sim2gse_castsequence_members.end() && actions != castsequence->second)
      throw std::runtime_error("sim2gse castsequence members do not match its block");
    for (size_t i = 0; i < actions.size(); ++i)
      fmt::print("S2GBLOCK\t{}\t{}\t{}\n", sim2gse_blocks.size(), i, actions[i]->signature_str);
    sim2gse_blocks.push_back(actions);
  }
  if ( sim2gse_blocks.empty() || sim2gse_blocks.size() > 128 )
    throw std::runtime_error("invalid sim2gse sequence length");
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
  bool sequence_pending_success = false;
  int sequence_step = -1;
  int sequence_member = -1;
  if (origin)
  {
    const auto step = static_cast<unsigned>((origin - 1) % sim2gse_blocks.size());
    const auto sequence = sim2gse_castsequence_members.find(step);
    if (sequence != sim2gse_castsequence_members.end())
    {
      sequence_step = static_cast<int>(step);
      const auto original = sim2gse_castsequence_origin_members.find(origin);
      sequence_member = static_cast<int>(original == sim2gse_castsequence_origin_members.end() ?
                                         sim2gse_castsequence_positions[step] : original->second);
      auto pending = sim2gse_castsequence_pending_origins.find(step);
      sequence_pending_success = native_execute && pending != sim2gse_castsequence_pending_origins.end() &&
                                 pending->second == origin;
      if (pending != sim2gse_castsequence_pending_origins.end() && pending->second == origin &&
          (native_execute || native_interrupt || std::string(event) == "dispatch_failed" ||
           std::string(event) == "observed_failed" || std::string(event) == "queue_rollback" ||
           std::string(event) == "replace"))
        sim2gse_castsequence_pending_origins.erase(pending);
      if (std::string(event) == "queue_restore" && a == sequence->second[sequence_member] &&
          sim2gse_castsequence_origin_generations[origin] == sim2gse_castsequence_generations[step])
        sim2gse_castsequence_pending_origins[step] = origin;
    }
  }
  const bool direct = origin && a &&
    std::find(sim2gse_blocks[(origin - 1) % sim2gse_blocks.size()].begin(),
              sim2gse_blocks[(origin - 1) % sim2gse_blocks.size()].end(), a) !=
    sim2gse_blocks[(origin - 1) % sim2gse_blocks.size()].end();
  if (native_execute && direct)
  {
    sim2gse_executed_actions.emplace(origin, a);
    const auto step = static_cast<unsigned>((origin - 1) % sim2gse_blocks.size());
    const auto sequence = sim2gse_castsequence_members.find(step);
    if (sequence != sim2gse_castsequence_members.end() && sequence_pending_success)
    {
      auto& position = sim2gse_castsequence_positions[step];
      if (position >= sequence->second.size() || sequence->second[position] != a)
        throw std::runtime_error("sim2gse castsequence success does not match current member");
      position = (position + 1) % sequence->second.size();
    }
  }
  write_trace( event, a, origin, sequence_step, sequence_member, direct );
}

void controller_t::write_trace( const char* event, action_t* a, unsigned origin,
                                int sequence_step, int sequence_member, bool direct ) const
{
  if ( !sim2gse_trace ) return;
  if ( (std::string(event) == "native_execute" || std::string(event) == "native_interrupt") && !direct )
    event = "native_derived";
  owner_->sim->out_log.print("S2GSE\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}", owner_->sim->current_time().total_millis(),
      event, origin, origin ? static_cast<int>((origin - 1) % sim2gse_blocks.size()) : -1, a ? a->name_str : "-", owner_->gcd_ready.total_millis(),
      owner_->resources.current[owner_->primary_resource()], owner_->health_percentage(), a ? a->cooldown->remains().total_millis() : 0,
      owner_->sim->current_iteration, a ? a->signature_str : "-", a ? a->execute_time().total_millis() : 0,
      sequence_step, sequence_member);
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
  sim2gse_step = (sim2gse_step + 1) % sim2gse_blocks.size();
  schedule_next();
}

}
