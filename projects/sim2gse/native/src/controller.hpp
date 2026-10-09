#pragma once

#include "util/timespan.hpp"
#include <vector>

struct player_t;

namespace sim2gse
{
// Stage-2 lifecycle probe. Action/queue state moves here in the next ticket.
class controller_t
{
public:
  void initialize( player_t& );
  void reset( player_t& );
  void start( player_t& );
  void schedule_next( player_t& );
  unsigned advance_input() { return ++input_; }
  bool matches_input_time( timespan_t, unsigned origin ) const;

private:
  std::vector<timespan_t> input_times_;
  unsigned input_ = 0;
};
}
