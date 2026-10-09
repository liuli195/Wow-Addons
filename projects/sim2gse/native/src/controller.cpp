#include "controller.hpp"
#include "simulationcraft.hpp"

namespace sim2gse
{
void controller_t::initialize( player_t& owner )
{
  for (auto value : util::string_split(owner.sim2gse_times, "/"))
  {
    if (value.empty() || value.find_first_not_of("0123456789") != std::string::npos)
      throw std::runtime_error("invalid sim2gse input time");
    auto at = timespan_t::from_millis(std::stoul(value));
    if (at >= owner.sim->max_time || (!input_times_.empty() && at <= input_times_.back()))
      throw std::runtime_error("sim2gse input times must increase within combat");
    input_times_.push_back(at);
  }
  if (input_times_.size() > 4096)
    throw std::runtime_error("too many sim2gse input times");
  for (auto value : util::string_split(owner.sim2gse_gcd_states, "/"))
  {
    if (value.empty()) continue;
    const auto fields = util::string_split(value, ",");
    if (fields.size() != 2 ||
        fields[0].find_first_not_of("0123456789") != std::string::npos ||
        fields[1].find_first_not_of("0123456789") != std::string::npos)
      throw std::runtime_error("invalid sim2gse GCD feedback");
    owner.sim2gse_observed_gcd_states.emplace_back(
        timespan_t::from_millis(std::stoul(fields[0])),
        timespan_t::from_millis(std::stoul(fields[1])));
  }
  if (!owner.sim2gse_observed_gcd_states.empty() &&
      owner.sim2gse_observed_gcd_states.size() != input_times_.size())
    throw std::runtime_error("sim2gse GCD feedback must match input times");
  for (auto value : util::string_split(owner.sim2gse_failed_actions, "/"))
    owner.sim2gse_observed_failed_actions.push_back(value == "-" ? "" : value);
  if (!owner.sim2gse_observed_failed_actions.empty() &&
      owner.sim2gse_observed_failed_actions.size() != input_times_.size())
    throw std::runtime_error("sim2gse failure feedback must match input times");
  if (!owner.sim2gse_failed_actions.empty() && !owner.sim2gse_failure_events.empty())
    throw std::runtime_error("sim2gse failure feedback formats cannot be mixed");
  for (auto value : util::string_split(owner.sim2gse_failure_events, "/"))
  {
    if (value.empty()) continue;
    const auto fields = util::string_split(value, ",");
    if (fields.size() != 3 || fields[0].empty() || fields[1].empty() || fields[2].empty() ||
        fields[0].find_first_not_of("0123456789") != std::string::npos ||
        fields[1].find_first_not_of("0123456789") != std::string::npos)
      throw std::runtime_error("invalid sim2gse failure event");
    const auto at = timespan_t::from_millis(std::stoul(fields[0]));
    const auto from = static_cast<unsigned>(std::stoul(fields[1]));
    if (at >= owner.sim->max_time || from == 0 || from > input_times_.size() ||
        at < input_times_[from - 1])
      throw std::runtime_error("sim2gse failure event precedes its input or exceeds combat");
    owner.sim2gse_observed_failure_events.emplace_back(at, from, fields[2]);
  }
}

void controller_t::reset( player_t& owner )
{
  input_ = 0;
  owner.sim2gse_step = owner.sim2gse_pending_origin = owner.sim2gse_committed_origin = owner.sim2gse_origin = 0;
  for (auto& [step, position] : owner.sim2gse_castsequence_positions) position = 0;
  owner.sim2gse_castsequence_pending_origins.clear();
  owner.sim2gse_castsequence_origin_members.clear();
  owner.sim2gse_castsequence_generations.clear();
  owner.sim2gse_castsequence_origin_generations.clear();
  owner.sim2gse_castsequence_last_use.clear();
  owner.sim2gse_castsequence_clock_started = false;
  owner.sim2gse_precombat_gcd = owner.sim2gse_precombat_cast = owner.sim2gse_precombat_cast_ready = 0_ms;
  owner.sim2gse_client_gcd_ready = 0_ms;
  owner.sim2gse_last_observed_gcd_start = owner.sim2gse_last_observed_gcd_duration = 0_ms;
  owner.sim2gse_observed_gcd_initialized = false;
  owner.sim2gse_tentative_gcd_start = owner.sim2gse_tentative_gcd_duration = owner.sim2gse_tentative_old_gcd_start =
    owner.sim2gse_tentative_old_gcd_duration = 0_ms;
  owner.sim2gse_tentative_stable_reads = 0;
  owner.sim2gse_tentative_gcd = false;
  owner.sim2gse_waiting_confirmation = false;
  owner.sim2gse_confirmed_tentative_gcd = false;
  owner.sim2gse_confirmed_tentative_origin = 0;
  owner.sim2gse_confirmed_tentative_action = nullptr;
  owner.sim2gse_pending = owner.sim2gse_committed = owner.sim2gse_dispatch = nullptr;
  owner.sim2gse_candidates.clear();
  owner.sim2gse_executed_actions.clear();
  owner.sim2gse_deferred_dispatches.clear();
  owner.sim2gse_commit = owner.sim2gse_queue = nullptr;
}

void controller_t::start( player_t& owner )
{
  auto* player = &owner;
  make_event( *owner.sim, input_times_.empty() ? 0_ms : input_times_.front(),
              [player] { player->sim2gse_tick(); } );
}

void controller_t::schedule_next( player_t& owner )
{
  auto* player = &owner;
  if ( input_times_.empty() )
    make_event( *owner.sim, 300_ms, [player] { player->sim2gse_tick(); } );
  else if ( input_ < input_times_.size() )
    make_event( *owner.sim, input_times_[input_] - owner.sim->current_time(),
                [player] { player->sim2gse_tick(); } );
}

bool controller_t::matches_input_time( timespan_t at, unsigned origin ) const
{
  return at == input_times_[origin - 1];
}
}
