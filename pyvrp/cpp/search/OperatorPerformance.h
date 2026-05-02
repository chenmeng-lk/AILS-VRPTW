#ifndef PYVRP_SEARCH_OPERATORPERFORMANCE_H
#define PYVRP_SEARCH_OPERATORPERFORMANCE_H

#include <algorithm>
#include <cmath>
#include <limits>

namespace pyvrp::search
{
/**
 * OperatorPerformance
 *
 * Tracks the performance of a local search operator for adaptive operator
 * selection using the Multi-Armed Bandit (UCB) algorithm.
 *
 * Attributes
 * ----------
 * totalReward
 *     Cumulative reward assigned to this operator.
 * selectionCount
 *     Number of times this operator was selected for priority evaluation.
 * applicationCount
 *     Number of times this operator successfully applied an improving move.
 * avgReward
 *     EWMA reward per evaluation.
 */
struct OperatorPerformance
{
    double totalReward = 0.0;      // Total cumulative reward (for statistics)
    size_t selectionCount = 0;
    size_t applicationCount = 0;
    double avgReward = 0.0;        // EWMA reward (used for UCB)
    double alpha = 0.1;            // Learning rate for EWMA (0.1 = 10% weight to new reward)

    /**
     * Updates the performance metrics for a selected operator.
     *
     * Uses Exponentially Weighted Moving Average (EWMA) instead of cumulative
     * average, which gives more weight to recent rewards and allows the
     * operator to adapt to changing performance over time.
     *
     * Parameters
     * ----------
     * reward
     *     The reward obtained for this selection. Use zero when the selected
     *     operator did not lead to an applied move. In local search, this
     *     reward is used as a success signal rather than a raw
     *     cost-improvement magnitude.
     * applied
     *     Whether the operator was successfully applied.
     */
    void update(double reward, bool applied)
    {
        selectionCount++;

        // EWMA: avgReward = alpha * newReward + (1 - alpha) * oldAvgReward.
        // Failed evaluations should contribute a zero reward, otherwise the
        // moving average never decreases when an operator stops working well.
        if (selectionCount == 1)
            avgReward = reward;
        else
            avgReward = alpha * reward + (1.0 - alpha) * avgReward;

        if (applied)
        {
            applicationCount++;
            totalReward += reward;  // Keep total for statistics.
        }
    }

    /**
     * Sets the learning rate (alpha) for EWMA.
     *
     * Parameters
     * ----------
     * newAlpha
     *     Learning rate in range [0, 1]. Higher values give more weight
     *     to recent rewards (faster adaptation), lower values give more
     *     weight to historical performance (more stable).
     *     - alpha = 0.05: Very stable, slow adaptation
     *     - alpha = 0.1:  Default, balanced
     *     - alpha = 0.2:  Fast adaptation
     *     - alpha = 0.5:  Very reactive
     */
    void setAlpha(double newAlpha)
    {
        alpha = std::max(0.0, std::min(1.0, newAlpha));
    }

    /**
     * Computes the Upper Confidence Bound (UCB1) value for this operator.
     * The UCB balances exploitation (avgReward) and exploration (confidence).
     *
     * Parameters
     * ----------
     * totalSelections
     *     Total number of selections across all operators.
     * explorationFactor
     *     Exploration parameter (c in UCB formula). Default is sqrt(2).
     *     Higher values encourage more exploration.
     *
     * Returns
     * -------
     * double
     *     The UCB value. Returns infinity if never selected (to ensure
     *     all operators are tried at least once).
     */
    double computeUCB(size_t totalSelections, double explorationFactor = 1.414)
        const
    {
        // If never selected, return infinity to ensure exploration
        if (selectionCount == 0)
            return std::numeric_limits<double>::infinity();

        // UCB1 formula: avg_reward + c * sqrt(ln(total) / count)
        double exploitation = avgReward;
        double exploration = explorationFactor
                             * std::sqrt(std::log(static_cast<double>(
                                             totalSelections))
                                         / static_cast<double>(selectionCount));

        return exploitation + exploration;
    }

    /**
     * Returns the success rate of this operator.
     *
     * Returns
     * -------
     * double
     *     The ratio of applications to selections (in range [0, 1]).
     */
    double successRate() const
    {
        if (selectionCount == 0)
            return 0.0;
        return static_cast<double>(applicationCount)
               / static_cast<double>(selectionCount);
    }

    /**
     * Resets all performance metrics to initial state.
     */
    void reset()
    {
        totalReward = 0.0;
        selectionCount = 0;
        applicationCount = 0;
        avgReward = 0.0;
    }

    /**
     * Default comparison for sorting (higher UCB first).
     * Note: Requires totalSelections context, so this is mainly for API.
     */
    bool operator==(OperatorPerformance const &other) const = default;
};
}  // namespace pyvrp::search

#endif  // PYVRP_SEARCH_OPERATORPERFORMANCE_H
