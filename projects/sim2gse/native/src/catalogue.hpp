// 只读原生对象，集中生成目录和归属信息。
#ifndef SIM2GSE_CATALOGUE_HPP
#define SIM2GSE_CATALOGUE_HPP
#include "interfaces/sc_js.hpp"
struct player_t;
struct stats_t;
namespace sim2gse
{
unsigned base_spell_id( const player_t& player, unsigned id );
void write_player_report( js::JsonOutput root, const player_t& player, bool include_apl );
void write_damage_owner( js::JsonOutput node, const stats_t& stats );
}
#endif
