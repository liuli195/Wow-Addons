#pragma once

#include "util/timespan.hpp"
#include "interfaces/sc_js.hpp"
#include <map>
#include <set>
#include <string>
#include <tuple>
#include <unordered_map>
#include <vector>

struct player_t;
struct action_t;
struct event_t;
struct buff_t;
struct dot_t;

namespace sim2gse
{
enum class selection_kind { uncontrolled, controlled_idle, selected };
struct selection_t { selection_kind kind; action_t* action; };
enum class precombat_phase { before, after };

class controller_t
{
public:
  void register_options( player_t& );
  void initialize( player_t& );
  void start( player_t& );
  void reset( player_t& );
  bool enabled() const { return !sim2gse_steps.empty(); }
  std::string unavailable_reason( const std::string& signature ) const;
  void write_report( js::JsonOutput root ) const;
  selection_t select();
  void notify( const char* event, action_t*, unsigned origin );
  void observe_execute( action_t& );
  void observe_replacement( action_t* from, action_t* to );
  void execution_end( action_t* );
  void observe_buff( buff_t&, const char*, int old_stacks = 0, action_t* = nullptr, event_t* = nullptr );
  void finish_buff_observations();
  unsigned observe_dot( dot_t&, const char*, unsigned = 0, event_t* = nullptr );
  void finish_observations();
  void transfer_replacement( action_t* from, action_t* to );
  void precombat( action_t&, precombat_phase );
  unsigned origin() const { return sim2gse_origin; }
  unsigned exchange_origin( unsigned value );

private:
  player_t* owner_ = nullptr;
  std::vector<timespan_t> input_times_;
  std::string input_sources_text_;
  unsigned burst_offset_ = 0;
  std::vector<unsigned> input_steps_, source_origins_;
  std::vector<bool> burst_inputs_;
  unsigned input_ = 0;
  std::string sim2gse_steps;
  std::string optional_spell_ids_;
  std::map<unsigned, std::vector<std::tuple<unsigned, std::string, std::string>>> skipped_commands_;
  std::string sim2gse_castsequences;
  std::string sim2gse_castsequence_events;
  bool sim2gse_trace = false;
  bool sim2gse_timed_feedback = false;
  timespan_t sim2gse_window = 400_ms;
  std::string sim2gse_times;
  std::string sim2gse_gcd_states;
  std::string sim2gse_failed_actions;
  std::string sim2gse_failure_events;
  timespan_t sim2gse_precombat_gcd = 0_ms;
  timespan_t sim2gse_precombat_cast = 0_ms;
  timespan_t sim2gse_precombat_cast_ready = 0_ms;
  timespan_t sim2gse_client_gcd_ready = 0_ms;
  std::vector<std::pair<timespan_t, timespan_t>> sim2gse_observed_gcd_states;
  std::vector<std::string> sim2gse_observed_failed_actions;
  std::vector<std::tuple<timespan_t, unsigned, std::string>> sim2gse_observed_failure_events;
  std::vector<std::pair<action_t*, unsigned>> sim2gse_candidates;
  std::set<std::pair<unsigned, action_t*>> sim2gse_executed_actions;
  std::map<std::pair<unsigned, action_t*>, action_t*> issued_actions_;
  std::map<std::pair<unsigned, action_t*>, event_t*> sim2gse_deferred_dispatches;
  timespan_t sim2gse_last_observed_gcd_start = 0_ms;
  timespan_t sim2gse_last_observed_gcd_duration = 0_ms;
  bool sim2gse_observed_gcd_initialized = false;
  timespan_t sim2gse_tentative_gcd_start = 0_ms;
  timespan_t sim2gse_tentative_gcd_duration = 0_ms;
  timespan_t sim2gse_tentative_old_gcd_start = 0_ms;
  timespan_t sim2gse_tentative_old_gcd_duration = 0_ms;
  unsigned sim2gse_tentative_stable_reads = 0;
  bool sim2gse_tentative_gcd = false;
  bool sim2gse_waiting_confirmation = false;
  bool sim2gse_confirmed_tentative_gcd = false;
  unsigned sim2gse_confirmed_tentative_origin = 0;
  action_t* sim2gse_confirmed_tentative_action = nullptr;
  std::vector<std::vector<action_t*>> sim2gse_blocks;
  std::map<unsigned, std::vector<action_t*>> sim2gse_castsequence_members;
  std::map<unsigned, unsigned> sim2gse_castsequence_positions;
  std::map<unsigned, unsigned> sim2gse_castsequence_pending_origins;
  std::map<unsigned, unsigned> sim2gse_castsequence_origin_members;
  std::map<unsigned, unsigned> sim2gse_castsequence_generations;
  std::map<unsigned, unsigned> sim2gse_castsequence_origin_generations;
  std::map<unsigned, timespan_t> sim2gse_castsequence_timeouts;
  std::map<unsigned, timespan_t> sim2gse_castsequence_last_use;
  std::map<unsigned, unsigned> sim2gse_castsequence_reset_flags;
  std::vector<std::pair<timespan_t, unsigned>> sim2gse_castsequence_reset_events;
  std::map<timespan_t, unsigned> sim2gse_castsequence_modifiers;
  bool sim2gse_castsequence_clock_started = false;
  std::unordered_map<action_t*, unsigned> sim2gse_button_ids;
  unsigned sim2gse_step = 0, sim2gse_pending_origin = 0, sim2gse_committed_origin = 0, sim2gse_origin = 0;
  action_t* sim2gse_pending = nullptr;
  action_t* sim2gse_committed = nullptr;
  action_t* sim2gse_dispatch = nullptr;
  event_t* sim2gse_commit = nullptr;
  event_t* sim2gse_queue = nullptr;

  // A request is resolved once. No expressions or readiness probes are added.
  struct observation_object_t
  {
    std::string alias, kind, identity, base_button, from_action, qualification;
    action_t* action = nullptr;
    action_t* button = nullptr;
    buff_t* buff = nullptr;
    bool buff_unique = false;
    int resource = 0;
    std::vector<std::pair<std::string, std::string>> components;
  };
  std::string observation_request_;
  std::vector<observation_object_t> observation_objects_;
  js::sc_js_t observations_;
  bool observation_active_ = false, observation_complete_ = false;
  unsigned observation_event_ = 0;
  std::map<action_t*, std::pair<unsigned, action_t*>> observation_execution_origins_;
  std::set<action_t*> observation_counted_actions_;
  struct buff_observation_t
  {
    unsigned instance = 0, changes = 0, schedule_changes = 0, natural_instance = 0, natural_changes = 0;
    bool active = false, complete = false, coverage = false, ambiguous = false, scheduling = false, natural = false;
    timespan_t start = timespan_t::min(), natural_deadline = timespan_t::min();
    event_t* natural_event = nullptr;
    action_t* consumer = nullptr;
    unsigned consume_instance = 0;
  };
  std::map<buff_t*, buff_observation_t> observation_buffs_;
  unsigned observation_buff_instance_ = 0;
  bool observation_buffs_active_ = false;
  struct dot_observation_t
  {
    unsigned instance = 0, changes = 0, natural_instance = 0, natural_changes = 0, token = 0, candidate = 0;
    bool active = false, complete = false, natural = false;
    timespan_t start = timespan_t::min(), deadline = timespan_t::min(), natural_deadline = timespan_t::min();
    event_t* natural_event = nullptr;
  };
  std::map<dot_t*, dot_observation_t> observation_dots_;
  std::map<std::string, bool> observation_dot_coverage_;
  std::map<std::string, action_t*> observation_qualification_sources_;
  bool observation_dots_active_ = false;
  unsigned observation_dot_token_ = 0;
  void write_dot_event( dot_t&, const char*, const char* = nullptr );
  void write_buff_event( buff_t&, const char*, const char*, action_t* = nullptr );
  void initialize_observations();
  void start_observations();
  void observe_input( unsigned );
  void observe_ready( action_t*, unsigned, bool );
  void observe_action( js::JsonOutput, action_t*, action_t* );
  void observe_unselected( unsigned );
  js::JsonOutput observation_row( const char*, unsigned, const std::string& = {} );


  void initialize_times();
  void initialize_sources();
  unsigned step_for_origin( unsigned ) const;
  void schedule_first_input();
  void schedule_next();
  bool matches_input_time( timespan_t, unsigned ) const;
  timespan_t sim2gse_action_delay( action_t*, bool );
  bool sim2gse_queue_requirements( action_t* );
  void sim2gse_finish_committed();
  void sim2gse_execute_committed();
  void sim2gse_commit_pending( bool defer_execution = false );
  void sim2gse_arm_queue();
  void sim2gse_init();
  void sim2gse_reset_castsequence( unsigned );
  void sim2gse_castsequence_update();
  void handle_event( const char*, action_t*, unsigned );
  void write_trace( const char*, action_t*, unsigned, int, int, action_t* ) const;
  void sim2gse_dispatch_action( action_t*, unsigned );
  void sim2gse_tick();
};
}
