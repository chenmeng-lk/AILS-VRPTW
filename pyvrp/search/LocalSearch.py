from pyvrp._pyvrp import (
    CostEvaluator,
    ProblemData,
    RandomNumberGenerator,
    Solution,
)
from pyvrp.search._search import (
    BinaryOperator,
    LocalSearchStatistics,
    PerturbationManager,
    UnaryOperator,
)
from pyvrp.search._search import LocalSearch as _LocalSearch


class LocalSearch:
    """
    Local search method. This search method explores a granular neighbourhood
    in a very efficient manner using user-provided operators. This quickly
    results in much improved solutions.

    Parameters
    ----------
    data
        Data object describing the problem to be solved.
    rng
        Random number generator.
    neighbours
        List of lists that defines the local search neighbourhood.
    perturbation_manager
        Perturbation manager that handles perturbation during each invocation.
    """

    def __init__(
        self,
        data: ProblemData,
        rng: RandomNumberGenerator,
        neighbours: list[list[int]],
        perturbation_manager: PerturbationManager = PerturbationManager(),
    ):
        self._ls = _LocalSearch(data, neighbours, perturbation_manager)
        self._rng = rng

    def add_operator(self, op: UnaryOperator | BinaryOperator):
        """
        Adds an operator to this local search object. The operator will be used
        to improve a solution.

        Parameters
        ----------
        op
            The operator to add to this local search object.
        """
        self._ls.add_operator(op)

    @property
    def neighbours(self) -> list[list[int]]:
        """
        Returns the granular neighbourhood currently used by the local search.
        """
        return self._ls.neighbours

    @neighbours.setter
    def neighbours(self, neighbours: list[list[int]]):
        """
        Convenience method to replace the current granular neighbourhood used
        by the local search object.
        """
        self._ls.neighbours = neighbours

    @property
    def unary_operators(self) -> list[UnaryOperator]:
        """
        Returns the unary operators in use.
        """
        return self._ls.unary_operators

    @property
    def binary_operators(self) -> list[BinaryOperator]:
        """
        Returns the binary operators in use.
        """
        return self._ls.binary_operators

    @property
    def statistics(self) -> LocalSearchStatistics:
        """
        Returns search statistics about the most recently improved solution.
        """
        return self._ls.statistics

    def __call__(
        self,
        solution: Solution,
        cost_evaluator: CostEvaluator,
        exhaustive: bool = False,
    ) -> Solution:
        """
        This method improves the given solution through a (default
        non-exhaustive) local search.

        Parameters
        ----------
        solution
            The solution to improve through local search.
        cost_evaluator
            Cost evaluator to use.
        exhaustive
            Performs an exhaustive, complete search if set. Otherwise does
            only a limited search over perturbed clients (default).

        Returns
        -------
        Solution
            The improved solution. This is not the same object as the
            solution that was passed in.
        """
        self._ls.shuffle(self._rng)
        return self._ls(solution, cost_evaluator, exhaustive)
    
    def print_operator_performance(self):
        """
        Prints the current performance statistics for all operators.
        Useful for debugging and understanding which operators are most effective.
        """
        print("\n" + "=" * 80)
        print("OPERATOR PERFORMANCE STATISTICS (UCB-based Adaptive Selection)")
        print("=" * 80)

        # Print unary operators
        if self._ls.unary_performance:
            print("\nUnary Operators:")
            print("-" * 80)
            for i, perf in enumerate(self._ls.unary_performance):
                ucb = perf.compute_ucb(max(1, sum(p.selection_count for p in self._ls.unary_performance)),
                                       self._ls.get_exploration_factor())
                print(f"  Op[{i}]: UCB={ucb:8.2f} | "
                      f"Avg Reward={perf.avg_reward:8.2f} | "
                      f"Selections={perf.selection_count:6d} | "
                      f"Applications={perf.application_count:6d} | "
                      f"Success Rate={perf.success_rate():6.1%}")

        # Print binary operators
        if self._ls.binary_performance:
            print("\nBinary Operators:")
            print("-" * 80)
            for i, perf in enumerate(self._ls.binary_performance):
                total_selections = max(1, sum(p.selection_count for p in self._ls.binary_performance))
                ucb = perf.compute_ucb(total_selections, self._ls.get_exploration_factor())
                print(f"  Op[{i}]: UCB={ucb:8.2f} | "
                      f"Avg Reward={perf.avg_reward:8.2f} | "
                      f"Selections={perf.selection_count:6d} | "
                      f"Applications={perf.application_count:6d} | "
                      f"Success Rate={perf.success_rate():6.1%}")

        print("\nExploration Factor: {:.3f}".format(self._ls.get_exploration_factor()))
        print("=" * 80 + "\n")
