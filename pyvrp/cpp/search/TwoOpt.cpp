#include "TwoOpt.h"
#include "Route.h"

#include <cassert>
#include <iostream>

using pyvrp::search::TwoOpt;

std::pair<pyvrp::Cost, bool> TwoOpt::evaluate(
    Route::Node *U, Route::Node *V, CostEvaluator const &costEvaluator)
{
    stats_.numEvaluations++;

    // Basic validation
    if (!U->route() || !V->route())
        return std::make_pair(0, false);

    // Must be on the same route
    if (U->route() != V->route())
        return std::make_pair(0, false);

    // Must be in the same trip
    if (U->trip() != V->trip())
        return std::make_pair(0, false);

    // U must come before V
    if (U->pos() >= V->pos())
        return std::make_pair(0, false);

    // Need at least four nodes in the segment [U+1, V] to make reversal meaningful
    if (V->pos() - U->pos() < 4)
        return std::make_pair(0, false);

    // U and V cannot be depots
    if (U->isDepot() || V->isDepot())
        return std::make_pair(0, false);

    auto const *route = U->route();

    // Check if any depot exists in the segment [U+1, V] that will be reversed
    for (size_t pos = U->pos() + 1; pos <= V->pos(); ++pos)
    {
        if (route->operator[](pos)->isDepot())
            return std::make_pair(0, false);
    }

    // Original: ... -> [0...U] -> [U+1...V] -> [V+1...end]
    // New:      ... -> [0...U] -> [V...U+1] -> [V+1...end]
    // General case: reverse the segment from U+1 to V
    Cost deltaCost = 0;
    auto const proposal = Route::Proposal(
        route->before(U->pos()),
        route->betweenReversed(U->pos() + 1, V->pos()),
        route->after(V->pos() + 1));

    costEvaluator.deltaCost(deltaCost, proposal);
    //if (deltaCost < 0) std::cout << "  deltaCost = " << deltaCost << std::endl;
    return std::make_pair(deltaCost, deltaCost < 0);
}

void TwoOpt::apply(Route::Node *U, Route::Node *V) const
{
    stats_.numApplications++;

    auto &route = *U->route();
    // std::cout << "[TwoOpt::apply] Before swap: route " << route.profile() << ":";
    // for (size_t i = 0; i < route.size(); ++i) {
    //     std::cout << " " << route[i]->idx();
    // }
    // std::cout << "\n  -> Reversing segment from pos " << U->pos() + 1
    //           << " to " << V->pos() << "\n";

    size_t left = U->pos() + 1;
    size_t right = V->pos();

    while (left < right)
    {
        Route::swap(route[left], route[right]);
        ++left;
        --right;
    }
    // 打印反转后路由
    // std::cout << "  After swap: route " << route.profile() << ":";
    // for (size_t i = 0; i < route.size(); ++i) {
    //     std::cout << " " << route[i]->idx();
    // }
    // std::cout << "\n";
}

template <> bool pyvrp::search::supports<TwoOpt>(ProblemData const &data)
{
    // Works for any instance with at least one vehicle
    return data.numVehicles() >= 1;
}