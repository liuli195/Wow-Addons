// 只读原生对象，集中生成目录和归属信息。
#ifndef SIM2GSE_CATALOGUE_HPP
#define SIM2GSE_CATALOGUE_HPP
#include "interfaces/sc_js.hpp"
#include <string>
#include <map>
#include <vector>
struct player_t;
struct stats_t;
struct action_t;
struct player_effect_t;
namespace sim2gse
{
struct static_action_t
{
  action_t* action;
  const action_t* cost_action;
  std::map<std::string, std::string> unknown;
};
unsigned base_spell_id( const player_t& player, unsigned id );
bool action_available( const action_t& action );
bool static_effects_safe( const std::vector<player_effect_t>& effects, bool benefit = false );
std::string unavailable_reason( const player_t& player, const std::string& signature,
                                const std::vector<unsigned>& spell_ids = {} );
void capture_static_snapshot( player_t& player, const std::vector<static_action_t>& actions,
                              const std::vector<const action_t*>& precombat_actions,
                              const std::map<std::string, double>& parameters,
                              const std::map<std::string, bool>& talents,
                              const std::map<std::string, std::string>& parameter_unknown );
void write_player_report( js::JsonOutput root, const player_t& player, bool include_apl );
void write_damage_owner( js::JsonOutput node, const stats_t& stats );
}
#endif
