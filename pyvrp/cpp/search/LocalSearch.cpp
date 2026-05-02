#include "LocalSearch.h"
#include "DynamicBitset.h"
#include "Measure.h"
#include "logging.h"

#include <algorithm>
#include <cassert>
#include <iterator>
#include <numeric>
#include <cmath>

using pyvrp::Solution;
using pyvrp::search::BinaryOperator;
using pyvrp::search::LocalSearch;
using pyvrp::search::SearchSpace;
using pyvrp::search::UnaryOperator;

namespace
{
size_t totalSelections(
    std::vector<pyvrp::search::OperatorPerformance> const &performance)
{
    return std::accumulate(performance.begin(),
                           performance.end(),
                           size_t(0),
                           [](size_t total,
                              pyvrp::search::OperatorPerformance const &perf)
                           { return total + perf.selectionCount; });
}

void rankOperatorOrder(std::vector<size_t> &order,
                       std::vector<pyvrp::search::OperatorPerformance> const
                           &performance,
                       size_t totalSelections,
                       double explorationFactor,
                       pyvrp::RandomNumberGenerator &rng)
{
    rng.shuffle(order.begin(), order.end());

    std::stable_sort(order.begin(),
                     order.end(),
                     [&](size_t lhs, size_t rhs)
                     {
                         double lhsUcb = performance[lhs].computeUCB(
                             totalSelections, explorationFactor);
                         double rhsUcb = performance[rhs].computeUCB(
                             totalSelections, explorationFactor);
                         return lhsUcb > rhsUcb;
                     });
}
}  // namespace

pyvrp::Solution LocalSearch::operator()(pyvrp::Solution const &solution,
                                        CostEvaluator const &costEvaluator,
                                        bool exhaustive)
{
    PYVRP_DEBUG(
        "pyvrp.search", "Applying local search (exhaustive={}).", exhaustive);

    std::fill(lastTest_.begin(), lastTest_.end(), -1);
    std::fill(lastUpdate_.begin(), lastUpdate_.end(), 0);
    numUpdates_ = 0;

    solution_.load(solution);

    for (auto *op : unaryOps_)
        op->init(solution_);

    for (auto *op : binaryOps_)
        op->init(solution_);

    if (exhaustive)
        searchSpace_.markAllPromising();
    else
        perturbationManager_.perturb(solution_, searchSpace_, costEvaluator);

    ensureStructuralFeasibility(costEvaluator);
    search(costEvaluator);

    [[maybe_unused]] auto const stats = statistics();
    PYVRP_DEBUG("pyvrp.search",
                "Completed local search: improving={}, updates={}, moves={}.",
                stats.numImproving,
                stats.numUpdates,
                stats.numMoves);

    return solution_.unload();
}

void LocalSearch::search(CostEvaluator const &costEvaluator)
{
    if (unaryOps_.empty() && binaryOps_.empty())
        return;

    searchCompleted_ = false;
    for (int step = 0; !searchCompleted_; ++step)
    {
        PYVRP_DEBUG("pyvrp.search", "Entering search loop (step={}).", step);
        searchCompleted_ = true;

        for (auto const uClient : searchSpace_.clientOrder())
        {
            auto *U = &solution_.nodes[uClient];
            if (!searchSpace_.isPromising(uClient))
                continue;

            auto const lastTest = lastTest_[uClient];
            lastTest_[uClient] = numUpdates_;

            applyUnaryOps(U, costEvaluator);

            for (auto const vClient : searchSpace_.neighboursOf(uClient))
            {
                auto *V = &solution_.nodes[vClient];

                if (!V->route())
                    continue;

                auto *routes = solution_.routes.data();
                auto uUpdate = 0;
                if (U->route())
                    uUpdate = lastUpdate_[std::distance(routes, U->route())];
                auto vUpdate = lastUpdate_[std::distance(routes, V->route())];
                if (uUpdate > lastTest || vUpdate > lastTest)
                {
                    if (applyBinaryOps(U, V, costEvaluator))
                        continue;

                    if (p(V)->isStartDepot()
                        && applyBinaryOps(U, p(V), costEvaluator))
                        continue;
                }
            }

            // Moves involving empty routes are not tested initially to avoid
            // using too many routes, but we will try it if we have not been
            // able to insert U yet (perhaps the solution is empty?).
            if (step > 0 || !U->route())
                applyEmptyRouteMoves(U, costEvaluator);
        }
    }
}

void LocalSearch::shuffle(RandomNumberGenerator &rng)
{
    perturbationManager_.shuffle(rng);
    searchSpace_.shuffle(rng);

    // Use UCB (Upper Confidence Bound) algorithm to order operators instead of random shuffling.
    // This balances exploitation (using operators with high average reward) and exploration (trying
    // operators that haven't been selected much).

    // Sort unary operators by UCB value (highest first)
    if (!unaryOps_.empty())
    {
        totalUnarySelections_ = std::max<size_t>(1, totalSelections(unaryPerformance_));
        rankOperatorOrder(unaryOrder_,
                          unaryPerformance_,
                          totalUnarySelections_,
                          explorationFactor_,
                          rng);
    }

    // Sort binary operators by UCB value (highest first)
    if (!binaryOps_.empty())
    {
        totalBinarySelections_
            = std::max<size_t>(1, totalSelections(binaryPerformance_));
        rankOperatorOrder(binaryOrder_,
                          binaryPerformance_,
                          totalBinarySelections_,
                          explorationFactor_,
                          rng);
    }
}

bool LocalSearch::applyUnaryOps(Route::Node *U,
                                CostEvaluator const &costEvaluator)
{
    if (unaryOrder_.empty())
        return false;
    auto const selectedOpIdx = unaryOrder_.front();
    for (auto const opIdx : unaryOrder_)
    {
        auto *op = unaryOps_[opIdx];
        auto const [deltaCost, shouldApply] = op->evaluate(U, costEvaluator);
        if (shouldApply)
        {
            PYVRP_DEBUG("pyvrp.search",
                        "Applying operator to U={} (delta={}).",
                        U->idx(),
                        deltaCost);

            auto *rU = U->route();
            if (rU)
                searchSpace_.markPromising(U);

            [[maybe_unused]] auto const costBefore
                = costEvaluator.penalisedCost(solution_);

            op->apply(U);
            if (!rU)  // then U wasn't in the solution before, and the operator
            {         // just inserted it.
                rU = U->route();
                searchSpace_.markPromising(U);
            }

            update(rU, rU);

            [[maybe_unused]] auto const costAfter
                = costEvaluator.penalisedCost(solution_);

            // Update operator performance using a bounded success reward.
            // This keeps the UCB signal focused on operator success rate,
            // rather than letting a rare large improvement dominate ordering.
            unaryPerformance_[selectedOpIdx].update(opIdx == selectedOpIdx ? 1.0 : 0.0,
                                                    opIdx == selectedOpIdx);

            // When there is an improving move, the delta cost evaluation must
            // be exact. The resulting cost is then the sum of the cost before
            // the move, plus the delta cost.
            assert(costAfter == costBefore + deltaCost);

            return true;
        }
    }
    unaryPerformance_[selectedOpIdx].update(0.0, false);
    return false;
}

bool LocalSearch::applyBinaryOps(Route::Node *U,
                                 Route::Node *V,
                                 CostEvaluator const &costEvaluator)
{
    if (binaryOrder_.empty())
        return false;
    auto const selectedOpIdx = binaryOrder_.front();
    for (auto const opIdx : binaryOrder_)
    {
        auto *op = binaryOps_[opIdx];
        auto const [deltaCost, shouldApply] = op->evaluate(U, V, costEvaluator);
        if (shouldApply)
        {
            PYVRP_DEBUG("pyvrp.search",
                        "Applying operator to U={} and V={} (delta={}).",
                        U->idx(),
                        V->idx(),
                        deltaCost);

            auto *rU = U->route();
            auto *rV = V->route();
            assert(rV);

            if (rU)
                searchSpace_.markPromising(U);
            searchSpace_.markPromising(V);

            [[maybe_unused]] auto const costBefore
                = costEvaluator.penalisedCost(solution_);

            op->apply(U, V);
            update(rU, rV);

            [[maybe_unused]] auto const costAfter
                = costEvaluator.penalisedCost(solution_);

            // Update operator performance using a bounded success reward.
            binaryPerformance_[selectedOpIdx].update(opIdx == selectedOpIdx ? 1.0 : 0.0,
                                                     opIdx == selectedOpIdx);

            // When there is an improving move, the delta cost evaluation must
            // be exact. The resulting cost is then the sum of the cost before
            // the move, plus the delta cost.
            assert(costAfter == costBefore + deltaCost);

            return true;
        }
    }
    binaryPerformance_[selectedOpIdx].update(0.0, false);
    return false;
}

void LocalSearch::applyEmptyRouteMoves(Route::Node *U,
                                       CostEvaluator const &costEvaluator)
{
    // We apply moves involving empty routes in the (randomised) order of
    // orderVehTypes. This helps because empty vehicle moves incur fixed cost,
    // and a purely greedy approach over-prioritises vehicles with low fixed
    // costs but possibly high variable costs.
    for (auto const &[vehType, offset] : searchSpace_.vehTypeOrder())
    {
        auto const begin = solution_.routes.begin() + offset;
        auto const end = begin + data.vehicleType(vehType).numAvailable;
        auto const pred = [](auto const &route) { return route.empty(); };
        auto empty = std::find_if(begin, end, pred);

        if (empty != end && applyBinaryOps(U, (*empty)[0], costEvaluator))
            break;
    }
}

void LocalSearch::ensureStructuralFeasibility(
    CostEvaluator const &costEvaluator)
{
    std::vector<size_t> groupCount(data.numGroups(), 0);  // tracks membership
    for (size_t idx = 0; idx != data.numGroups(); ++idx)  // count in solution
    {
        auto const &group = data.group(idx);
        for (auto const client : group)
            if (solution_.nodes[client].route())
                groupCount[idx]++;
    }

    // Ensure all required clients and groups are present in the solution.
    for (auto const client : searchSpace_.clientOrder())
    {
        auto &node = solution_.nodes[client];
        auto const &clientData = data.client(client);

        if (!node.route() && clientData.required)  // then we must insert
        {
            solution_.insert(&node, searchSpace_, costEvaluator, true);
            update(node.route(), node.route());
            searchSpace_.markPromising(&node);
            continue;
        }

        if (clientData.group)
        {
            auto const idx = *clientData.group;
            auto const &group = data.group(idx);

            if (group.required && groupCount[idx] == 0)  // then we must insert
            {
                assert(!node.route());
                solution_.insert(&node, searchSpace_, costEvaluator, true);
                update(node.route(), node.route());
                searchSpace_.markPromising(&node);
                groupCount[idx]++;
                continue;
            }

            if (node.route() && groupCount[idx] > 1)  // then we must remove
            {
                searchSpace_.markPromising(&node);
                auto *route = node.route();
                route->remove(node.pos());
                update(route, route);
                groupCount[idx]--;
            }
        }
    }

#ifndef NDEBUG
    // Debug checks to ensure we have restored structural feasibility.
    for (size_t idx = 0; idx != data.numClients(); ++idx)
    {
        auto const &node = solution_.nodes[idx];
        auto const &clientData = data.client(idx);
        assert(node.route() || !clientData.required);
    }

    for (size_t idx = 0; idx != data.numGroups(); ++idx)
    {
        auto const &group = data.group(idx);
        assert(group.required ? groupCount[idx] == 1 : groupCount[idx] <= 1);
    }
#endif
}

void LocalSearch::update(Route *U, Route *V)
{
    assert(V);
    numUpdates_++;
    searchCompleted_ = false;

    auto const update = [&](Route *route)
    {
        route->update();
        if (route->empty())  // if route turned empty we clear it to remove any
            route->clear();  // lingering non-client nodes.

        auto const idx = std::distance(solution_.routes.data(), route);
        lastUpdate_[idx] = numUpdates_;
    };

    if (U)
        update(U);

    if (U != V)
        update(V);
}

void LocalSearch::addOperator(UnaryOperator &op)
{
    unaryOps_.emplace_back(&op);
    unaryPerformance_.emplace_back();  // Add corresponding performance tracker
    unaryOrder_.push_back(unaryOrder_.size());
}

void LocalSearch::addOperator(BinaryOperator &op)
{
    binaryOps_.emplace_back(&op);
    binaryPerformance_.emplace_back();  // Add corresponding performance tracker
    binaryOrder_.push_back(binaryOrder_.size());
}

std::vector<UnaryOperator *> const &LocalSearch::unaryOperators() const
{
    return unaryOps_;
}

std::vector<BinaryOperator *> const &LocalSearch::binaryOperators() const
{
    return binaryOps_;
}

void LocalSearch::setNeighbours(SearchSpace::Neighbours neighbours)
{
    searchSpace_.setNeighbours(neighbours);
}

SearchSpace::Neighbours const &LocalSearch::neighbours() const
{
    return searchSpace_.neighbours();
}

LocalSearch::Statistics LocalSearch::statistics() const
{
    size_t numMoves = 0;
    size_t numImproving = 0;

    auto const count = [&](auto const *op)
    {
        auto const &stats = op->statistics();
        numMoves += stats.numEvaluations;
        numImproving += stats.numApplications;
    };

    std::for_each(unaryOps_.begin(), unaryOps_.end(), count);
    std::for_each(binaryOps_.begin(), binaryOps_.end(), count);

    assert(numImproving <= numUpdates_);
    return {numMoves, numImproving, numUpdates_};
}

LocalSearch::LocalSearch(ProblemData const &data,
                         SearchSpace::Neighbours neighbours,
                         PerturbationManager &perturbationManager)
    : data(data),
      solution_(data),
      searchSpace_(data, neighbours),
      perturbationManager_(perturbationManager),
      lastTest_(data.numClients()),
      lastUpdate_(data.numVehicles())
{
}

void LocalSearch::setExplorationFactor(double factor)
{
    explorationFactor_ = factor;
}

double LocalSearch::getExplorationFactor() const
{
    return explorationFactor_;
}

std::vector<pyvrp::search::OperatorPerformance> const &
LocalSearch::unaryPerformance() const
{
    return unaryPerformance_;
}

std::vector<pyvrp::search::OperatorPerformance> const &
LocalSearch::binaryPerformance() const
{
    return binaryPerformance_;
}

void LocalSearch::resetOperatorPerformance()
{
    for (auto &perf : unaryPerformance_)
        perf.reset();
    for (auto &perf : binaryPerformance_)
        perf.reset();
    totalUnarySelections_ = 0;
    totalBinarySelections_ = 0;
}

void LocalSearch::setOperatorAlpha(double alpha)
{
    for (auto &perf : unaryPerformance_)
        perf.setAlpha(alpha);
    for (auto &perf : binaryPerformance_)
        perf.setAlpha(alpha);
}
