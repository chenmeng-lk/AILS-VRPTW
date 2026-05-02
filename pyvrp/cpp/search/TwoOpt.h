#ifndef PYVRP_SEARCH_TWOOPT_H
#define PYVRP_SEARCH_TWOOPT_H

#include "LocalSearchOperator.h"

namespace pyvrp::search
{
/**
 * The 2-OPT operator for a single route. Given two nodes :math:`i` and
 * :math:`j` in the same route where :math:`i < j`, the operator reverses
 * the segment from :math:`i+1` to :math:`j` (inclusive).
 *
 * This operator only works within a single trip. Both nodes must be in
 * the same trip for the move to be valid.
 */
class TwoOpt : public BinaryOperator
{
    using BinaryOperator::BinaryOperator;

public:
    std::pair<Cost, bool> evaluate(Route::Node *U,
                                   Route::Node *V,
                                   CostEvaluator const &costEvaluator) override;

    void apply(Route::Node *U, Route::Node *V) const override;
};

template <> bool supports<TwoOpt>(ProblemData const &data);
}  // namespace pyvrp::search

#endif  // PYVRP_SEARCH_TWOOPT_H