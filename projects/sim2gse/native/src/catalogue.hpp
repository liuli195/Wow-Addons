// 只读原生对象，集中生成目录和归属信息。
#ifndef SIM2GSE_CATALOGUE_HPP
#define SIM2GSE_CATALOGUE_HPP
#include "interfaces/sc_js.hpp"
#include <string>
#include <map>
#include <vector>
struct player_t;
struct stats_t;
namespace sim2gse
{
unsigned base_spell_id( const player_t& player, unsigned id );
std::string unavailable_reason( const player_t& player, const std::string& signature,
                                const std::vector<unsigned>& spell_ids = {} );
void capture_static_snapshot( player_t& player, const std::vector<std::string>& actions,
                              const std::map<std::string, double>& parameters,
                              const std::map<std::string, bool>& talents );
void write_player_report( js::JsonOutput root, const player_t& player, bool include_apl );
void write_damage_owner( js::JsonOutput node, const stats_t& stats );
}
#endif
