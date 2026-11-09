// Business counts only: never asks whether an action is ready or changes combat.
#include "sim2gse/catalogue.hpp"
#include "simulationcraft.hpp"
#include "player/action_priority_list.hpp"
#include <map>
#include <set>

namespace sim2gse
{
namespace
{
struct point_t { std::string button; int step = -1; unsigned segment = 0; };
struct input_t
{
  action_t* command = nullptr;
  unsigned origin = 0;
  int step = -1;
  bool burst = false;
  double at = 0;
};
struct summary_t
{
  std::string buttons_text, excluded_text, windows_text;
  std::set<std::string> allowed, excluded;
  std::vector<std::pair<double, double>> windows;
  std::map<action_t*, input_t> inputs;
  std::set<std::pair<unsigned, std::string>> completed;
  std::map<std::string, unsigned> successes, pairs, outgoing, positions;
  std::map<std::string, std::vector<int>> witnesses;
  point_t previous, before_previous, pending;
  bool pending_valid = false;
  unsigned samples = 0;
  unsigned long long duration_ms = 0;
  bool controlled = false;
  double last_at = -1;
};
// Product simulations are single-threaded. State belongs to the native process,
// not a Python task/group, and stays bounded by its actor/button/input limits.
thread_local std::map<const player_t*, summary_t> summaries;

bool apl_button(const action_t& a)
{
  if (!a.action_list) return false;
  const auto& list = *a.action_list;
  return range::find(list.foreground_action_list, &a) != list.foreground_action_list.end() ||
         range::find(list.off_gcd_actions, &a) != list.off_gcd_actions.end() ||
         range::find(list.cast_while_casting_actions, &a) != list.cast_while_casting_actions.end();
}
std::string button_key(const action_t& a)
{
  if (a.name_str == "use_item") return a.signature_str;
  if (a.name_str == "auto_attack") return "auto_attack";
  const auto id = base_spell_id(*a.player, a.data().id());
  return id ? "spell:" + std::to_string(id) : a.signature_str;
}
unsigned segment_for(const summary_t& s, double at)
{
  unsigned segment = 0;
  for (const auto& window : s.windows)
  {
    if (at >= window.first) ++segment;
    if (at >= window.second) ++segment;
  }
  return segment;
}
void finish_point(summary_t& s)
{
  if (!s.pending_valid) return;
  const auto current = s.pending;
  if (!s.previous.button.empty() && s.previous.segment == current.segment)
  {
    ++s.pairs[s.previous.button + ">" + current.button];
    ++s.outgoing[s.previous.button];
    if (!s.before_previous.button.empty() && s.before_previous.segment == current.segment &&
        s.before_previous.step >= 0 && s.previous.step >= 0 && current.step >= 0)
    {
      const auto witness_key = s.before_previous.button + ">" + current.button;
      if (!s.witnesses.count(witness_key))
        s.witnesses[witness_key] = {s.before_previous.step, s.previous.step, current.step};
    }
  }
  s.before_previous = s.previous;
  s.previous = current;
  s.pending_valid = false;
}

bool effective(const player_t& p)
{
  return p.sim->iterations <= 1 || p.sim->current_iteration > 0;
}
}

void summary_options(player_t& p)
{
  auto& s = summaries[&p];
  p.add_option(opt_string("sim2gse_summary_buttons", s.buttons_text));
  p.add_option(opt_string("sim2gse_summary_exclude", s.excluded_text));
  p.add_option(opt_string("sim2gse_summary_windows", s.windows_text));
}

void summary_begin(player_t& p)
{
  if (p.is_pet()) return;
  auto& s = summaries[&p];
  s.inputs.clear(); s.completed.clear(); s.previous = {}; s.before_previous = {};
  s.allowed.clear(); s.excluded.clear(); s.windows.clear(); s.controlled = false; s.last_at = -1; s.pending_valid = false;
  if (s.buttons_text != "@apl")
    for (const auto& key : util::string_split(s.buttons_text, "/")) s.allowed.insert(key);
  if (s.buttons_text.empty() || s.buttons_text == "@apl")
    for (const auto* a : p.action_list)
      if (apl_button(*a) && !a->is_precombat && (!a->background || a->name_str == "use_item") && !a->quiet &&
          a->initialized && ((a->data().ok() && a->data().id() && !a->data().flags(SX_PASSIVE)) ||
                              a->name_str == "auto_attack" || a->name_str == "use_item"))
        s.allowed.insert(button_key(*a));
  for (const auto& key : util::string_split(s.excluded_text, "/")) s.excluded.insert(key);
  for (const auto& text : util::string_split(s.windows_text, "/"))
  {
    const auto bounds = util::string_split(text, ",");
    if (bounds.size() != 2) throw std::runtime_error("invalid summary window");
    const auto start = util::to_int(bounds[0]), end = util::to_int(bounds[1]);
    if (start < 0 || end <= start || end > 180000) throw std::runtime_error("invalid summary window");
    s.windows.emplace_back(start, end);
  }
}

void summary_input(player_t& p, action_t* action, action_t* command,
                   unsigned origin, int step, bool burst, double at)
{
  if (p.is_pet()) return;
  auto& s = summaries[&p];
  s.controlled = true;
  if (action && command) s.inputs[action] = {command, origin, step, burst, at};
}

void summary_success(action_t& action)
{
  auto& p = *action.player;
  if (p.is_pet() || action.is_precombat || !effective(p)) return;
  auto& s = summaries[&p];
  const auto found = s.inputs.find(&action);
  const input_t* input = found == s.inputs.end() ? nullptr : &found->second;
  if (s.controlled && !input) return; // No dispatched player command owns this effect.
  const auto* command = input ? input->command : &action;
  if (!input && ((action.background && action.name_str != "use_item") || action.quiet || action.data().flags(SX_PASSIVE))) return;
  if ((!command->data().ok() || command->data().id() == 0) &&
      command->name_str != "auto_attack" && command->name_str != "use_item") return;
  const auto key = button_key(*command);
  if (!s.allowed.count(key))
  {
    if (!input && !apl_button(action)) return; // Known derived action, not an APL button or dispatched command.
    if (!input || (!s.buttons_text.empty() && s.buttons_text != "@apl"))
      throw std::runtime_error("unknown player summary button: " + key);
    s.allowed.insert(key);
  }
  if (input && !s.completed.emplace(input->origin, key).second) return;
  const double at = p.sim->current_time().total_millis();
  if (at > s.last_at) finish_point(s);
  else
  {
    s.pending_valid = false;
    s.previous = {}; s.before_previous = {};
  }
  if ((input && input->burst) || s.excluded.count(key))
  {
    s.previous = {}; s.before_previous = {}; s.pending_valid = false;
    s.last_at = at;
    return;
  }
  ++s.successes[key];
  const int step = input ? input->step : -1;
  if (step >= 0) ++s.positions[key + "@" + std::to_string(step)];
  if (at <= s.last_at)
  {
    s.previous = {}; s.before_previous = {};
    s.last_at = at;
    return; // Same-time success has no unambiguous predecessor or successor.
  }
  s.last_at = at;
  const auto segment = segment_for(s, at);
  if (input && segment_for(s, input->at) != segment)
  {
    s.previous = {}; s.before_previous = {};
    return; // Count delayed success but never bridge its original window.
  }
  s.pending = {key, step, segment};
  s.pending_valid = true;
}

void summary_end(player_t& p)
{
  if (p.is_pet() || !effective(p)) return;
  auto& s = summaries[&p];
  finish_point(s);
  ++s.samples;
  s.duration_ms += static_cast<unsigned long long>(p.sim->current_time().total_millis());
}

void summary_report(js::JsonOutput root, const player_t& p)
{
  if (p.is_pet()) return;
  const auto& s = summaries[&p];
  auto row = root["sim2gse_action_summary"];
  auto allowed = row["scope"]["allowed"];
  for (const auto& key : s.allowed) allowed[key] = true;
  auto excluded = row["scope"]["excluded"];
  for (const auto& key : s.excluded) excluded[key] = true;
  row["scope"]["windows"] = s.windows_text;
  row["scope"]["policy"] = s.buttons_text;
  row["scope"]["controlled"] = s.controlled;
  row["version"] = 1;
  row["samples"] = s.samples;
  row["duration_ms"] = s.duration_ms;
  auto write = [&](const char* name, const std::map<std::string, unsigned>& values) {
    auto field = row[name];
    for (const auto& value : values) field[value.first] = value.second;
  };
  write("successes", s.successes); write("pairs", s.pairs);
  write("outgoing", s.outgoing); write("positions", s.positions);
  auto witnesses = row["witnesses"];
  for (const auto& value : s.witnesses)
  {
    auto witness = witnesses[value.first]; witness.make_array();
    for (const auto position : value.second) witness.add(position);
  }
}
}
