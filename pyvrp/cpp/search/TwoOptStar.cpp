#include "TwoOptStar.h"
#include "Route.h"
#include <cassert>
using pyvrp::search::TwoOptStar;

std::pair<pyvrp::Cost, bool> TwoOptStar::evaluate(
    Route::Node *U, Route::Node *V, CostEvaluator const &costEvaluator)
{
    stats_.numEvaluations++;

    auto const *uRoute = U->route();
    auto const *vRoute = V->route();

    if (!uRoute || uRoute == vRoute)
        return std::make_pair(0, false);  // unassigned, or same route

    // Split operator cannot handle routes with multiple trips (reload depots)
    if (uRoute->numTrips() > 1 || vRoute->numTrips() > 1)
        return std::make_pair(0, false);

    // Split operator requires both U and V to have nodes before and after them
    // U must have: head1 (nodes before U) and tail1 (nodes after U)
    // V must have: head2 (nodes before V) and tail2 (nodes after V)
    bool hasHead1 = U->pos() > 1;           // U has nodes before it
    bool hasTail1 = !n(U)->isEndDepot();    // U has nodes after it
    bool hasHead2 = V->pos() > 1;           // V has nodes before it
    bool hasTail2 = !n(V)->isEndDepot();    // V has nodes after it

    if (!hasHead1 || !hasTail1 || !hasHead2 || !hasTail2)
        return std::make_pair(0, false);  // not enough nodes for Split

    Cost deltaCost = 0;

    // Build proposals for the TwoOptStar operation:
    // New route 1: U_before + reverse(V_before)
    // New route 2: reverse(U+1_after) + V+1_after
    auto const uProposal
        = Route::Proposal(uRoute->before(U->pos()),
                          vRoute->betweenReversed(1, V->pos()),
                          uRoute->at(uRoute->size() - 1));

    auto const vProposal
        = Route::Proposal(vRoute->at(0),
                          uRoute->betweenReversed(U->pos() + 1, uRoute->size() - 2),
                          vRoute->after(V->pos() + 1));

    costEvaluator.deltaCost(deltaCost, uProposal, vProposal);
    //if (deltaCost < 0) std::cout << "  deltaCost = " << deltaCost << std::endl;
    return std::make_pair(deltaCost, deltaCost < 0);
}

void TwoOptStar::apply(Route::Node *U, Route::Node *V) const
{
    stats_.numApplications++;

    auto *uRoute = U->route();
    auto *vRoute = V->route();

    // TwoOptStar operator should only be applied to routes with a single trip
    assert(uRoute->numTrips() == 1);
    assert(vRoute->numTrips() == 1);

    auto *nU = n(U);

    // Step 1: Collect tail1 (nodes after U) BEFORE modifying routes
    std::vector<Route::Node *> tail1;
    auto *current = nU;
    while (!current->isEndDepot())
    {
        tail1.push_back(current);
        current = n(current);
    }

    // Step 2: Remove V and head2 from route 2, insert in reverse order after U
    auto insertIdx = U->pos() + 1;
    auto *node = V;
    auto vPos = V->pos();

    // Remove V and insert it after U
    vRoute->remove(node->pos());
    uRoute->insert(insertIdx++, node);

    // Remove and insert nodes before V (head2) in reverse order
    while (vPos > 1)
    {
        vPos--;
        node = vRoute->operator[](vPos);
        vRoute->remove(node->pos());
        uRoute->insert(insertIdx++, node);
    }

    // Step 3: Remove tail1 from route 1, insert in reverse order into route 2
    insertIdx = 1;
    for (auto it = tail1.rbegin(); it != tail1.rend(); ++it)
    {
        node = *it;
        uRoute->remove(node->pos());
        vRoute->insert(insertIdx++, node);
    }
}

template <> bool pyvrp::search::supports<TwoOptStar>(ProblemData const &data)
{
    // Does not work for TSP, since the operator needs at least two routes.
    return data.numVehicles() > 1;
}