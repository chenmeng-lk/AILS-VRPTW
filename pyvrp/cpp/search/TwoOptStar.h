#ifndef PYVRP_SEARCH_TwoOptStar_H
#define PYVRP_SEARCH_TwoOptStar_H

#include "LocalSearchOperator.h"

namespace pyvrp::search
{
/**
 * TwoOptStar
 * Given two nodes :math:`U` and :math:`V` from different routes, the TwoOptStar
 * operator cuts both routes at these nodes and recombines them by swapping
 * segments with reversal.
 *
 * Specifically, where:
 * - Route 1: depot -> head1 -> U -> tail1 -> depot
 * - Route 2: depot -> head2 -> V -> tail2 -> depot
 *
 * After applying TwoOptStar at nodes U and V:
 * - Route 1: depot -> head1 -> U -> V -> reverse(head2 without start depot) -> depot
 * - Route 2: depot -> reverse(tail1 without end depot) -> tail2 -> depot
 *
 * Example:
 * - Route 1: depot -> a -> b -> 1 -> c -> d -> depot
 * - Route 2: depot -> e -> f -> j -> 2 -> h -> depot
 *
 * After TwoOptStar(1, 2):
 * - Route 1: depot -> a -> b -> 1 -> 2 -> j -> f -> e -> depot
 * - Route 2: depot -> d -> c -> h -> depot
 * This operator respects trip constraints and will only evaluate moves
 * that do not involve reload depots.
 */
class TwoOptStar : public BinaryOperator
{
    using BinaryOperator::BinaryOperator;

public:
    std::pair<Cost, bool> evaluate(Route::Node *U,
                                   Route::Node *V,
                                   CostEvaluator const &costEvaluator) override;

    void apply(Route::Node *U, Route::Node *V) const override;
};

template <> bool supports<TwoOptStar>(ProblemData const &data);
}  // namespace pyvrp::search

#endif  // PYVRP_SEARCH_TwoOptStar_H