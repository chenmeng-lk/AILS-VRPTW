#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
实验数据分析脚本（支持五种改进算法）
读取各算法多次运行结果（每个实例5个随机种子），计算每个算法的平均目标值与gap，
输出：
    - 表4‑1：总体性能对比（平均gap、中位数gap、胜出实例数、Wilcoxon检验）
    - 表4‑2：按问题类型与规模分组的平均gap
    - 表4‑3：各改进算法在每个分组上的胜/平/负计数

用法示例：
    python analyze_results_5improvements.py --baseline ILS_baseline.csv \\
        --tsla ILS_TSLA.csv --two_opt ILS_2opt.csv --two_opt_star ILS_2opt_star.csv \\
        --two_opt_and_star ILS_2opt_2optstar.csv --ucb ILS_UCB.csv
"""

import argparse
import re
import pandas as pd
import numpy as np
from scipy.stats import wilcoxon


def parse_instance_name(inst: str):
    m = re.match(r'CVRP/X-n(\d+)-k\d+', inst)
    if m:
        cust = int(m.group(1))
        return 'CVRP_X', cust
    if inst.startswith('CVRP/XXL/'):
        return 'CVRP_XXL', None
    if inst.startswith('VRPTW/'):
        return 'VRPTW', None
    return 'Unknown', None


def load_algorithm_results(csv_file: str, name: str):
    df = pd.read_csv(csv_file)
    required = ['Instance', 'Seed', 'Obj.', 'Best Obj.']
    for col in required:
        if col not in df.columns:
            raise ValueError(f"{csv_file} 缺少列 {col}")
    instances = df['Instance'].unique()
    data = {}
    for inst in instances:
        sub = df[df['Instance'] == inst]
        best = sub['Best Obj.'].iloc[0]
        mean_obj = sub['Obj.'].mean()
        data[inst] = {'mean_obj': mean_obj, 'best_obj': best}
    return data, name


def compute_gap(mean_obj, best_obj):
    return (mean_obj - best_obj) / best_obj * 100.0


def categorize_instance(inst: str, cust_count):
    if cust_count is not None:
        if cust_count <= 500:
            return 'CVRP X (≤500)'
        else:
            return 'CVRP X (>500)'
    if inst.startswith('CVRP/XXL/'):
        return 'CVRP XXL'
    if inst.startswith('VRPTW/'):
        return 'VRPTW'
    return 'Other'


def write_line(f, line):
    print(line)
    f.write(line + '\n')


def main():
    parser = argparse.ArgumentParser(description='分析CVRP/VRPTW实验结果（五种改进）')
    parser.add_argument('--baseline', required=True, help='基准算法CSV文件')
    parser.add_argument('--tsla', required=True, help='TSLA改进算法CSV文件')
    parser.add_argument('--two_opt', required=True, help='2opt改进算法CSV文件')
    parser.add_argument('--two_opt_star', required=True, help='2opt*改进算法CSV文件')
    parser.add_argument('--two_opt_and_star', required=True, help='2opt+2opt*改进算法CSV文件')
    parser.add_argument('--ucb', required=True, help='UCB改进算法CSV文件')
    parser.add_argument('--names', nargs=6, default=['ILS_baseline', 'ILS_TSLA', 'ILS_2opt', 
                                                     'ILS_2opt*', 'ILS_2opt+2opt*', 'ILS_UCB'],
                        help='算法显示名称，顺序：基准 TSLA 2opt 2opt* 2opt+2opt* UCB')
    parser.add_argument('--out', default='table_results.txt', help='输出结果文件')
    args = parser.parse_args()

    # 加载所有算法结果
    baseline_data, baseline_name = load_algorithm_results(args.baseline, args.names[0])
    tsla_data, tsla_name = load_algorithm_results(args.tsla, args.names[1])
    two_opt_data, two_opt_name = load_algorithm_results(args.two_opt, args.names[2])
    two_opt_star_data, two_opt_star_name = load_algorithm_results(args.two_opt_star, args.names[3])
    two_opt_and_star_data, two_opt_and_star_name = load_algorithm_results(args.two_opt_and_star, args.names[4])
    ucb_data, ucb_name = load_algorithm_results(args.ucb, args.names[5])

    # 收集所有改进算法信息
    improvements = [
        (tsla_data, tsla_name),
        (two_opt_data, two_opt_name),
        (two_opt_star_data, two_opt_star_name),
        (two_opt_and_star_data, two_opt_and_star_name),
        (ucb_data, ucb_name)
    ]

    # 检查实例一致性
    all_instances = set(baseline_data.keys())
    for data, _ in improvements:
        all_instances &= set(data.keys())
    if not all_instances:
        raise ValueError("算法文件之间没有公共的实例名称，请检查数据一致性。")

    # 存储每个实例的gap
    gaps = {baseline_name: []}
    for _, name in improvements:
        gaps[name] = []

    # 存储实例分类
    inst_categories = {}
    group_gaps = {baseline_name: {}}
    for _, name in improvements:
        group_gaps[name] = {}

    group_names = ['CVRP X (≤500)', 'CVRP X (>500)', 'CVRP XXL', 'VRPTW']
    for g in group_names:
        for alg in [baseline_name] + [name for _, name in improvements]:
            group_gaps[alg][g] = []

    # 遍历公共实例
    for inst in sorted(all_instances):
        best_obj = baseline_data[inst]['best_obj']
        # 基准
        base_mean = baseline_data[inst]['mean_obj']
        base_gap = compute_gap(base_mean, best_obj)
        gaps[baseline_name].append(base_gap)

        # 各改进算法
        for data, name in improvements:
            mean_obj = data[inst]['mean_obj']
            gp = compute_gap(mean_obj, best_obj)
            gaps[name].append(gp)

        # 分类
        _, cust = parse_instance_name(inst)
        group = categorize_instance(inst, cust)
        inst_categories[inst] = group
        # 存储分组gap
        for alg, g in [(baseline_name, base_gap)] + [(name, gaps[name][-1]) for _, name in improvements]:
            group_gaps[alg][group].append(g)

    # ========== 表4‑1：总体性能对比 ==========
    with open(args.out, 'w', encoding='utf-8') as f:
        write_line(f, "\n========== 表4‑1 总体性能对比 ==========")
        # 计算统计量
        results = []
        for alg in [baseline_name] + [name for _, name in improvements]:
            arr = np.array(gaps[alg])
            mean_gap = arr.mean()
            se = arr.std(ddof=1) / np.sqrt(len(arr))
            median_gap = np.median(arr)
            results.append((alg, mean_gap, se, median_gap))

        # 胜出计数 vs 基准
        wins = {name: 0 for _, name in improvements}
        ties = {name: 0 for _, name in improvements}
        losses = {name: 0 for _, name in improvements}
        for inst in all_instances:
            best_obj = baseline_data[inst]['best_obj']
            base_gap = compute_gap(baseline_data[inst]['mean_obj'], best_obj)
            for data, name in improvements:
                alg_gap = compute_gap(data[inst]['mean_obj'], best_obj)
                if alg_gap < base_gap:
                    wins[name] += 1
                elif alg_gap == base_gap:
                    ties[name] += 1
                else:
                    losses[name] += 1

        # Wilcoxon检验（单侧：改进算法gap < 基准gap）
        p_values = {}
        for _, name in improvements:
            stat, p = wilcoxon(gaps[baseline_name], gaps[name], alternative='greater')
            p_values[name] = p

        # 打印表头
        header = (f"{'算法':<18} {'平均 gap (%)':<22} {'中位数 gap (%)':<18} "
                  f"{'胜出实例数':<12} {'胜率':<8} {'Wilcoxon p值 (单侧)':<20}")
        write_line(f, header)
        for idx, alg in enumerate([baseline_name] + [name for _, name in improvements]):
            mean_g, se_g, med_g = results[idx][1], results[idx][2], results[idx][3]
            if alg == baseline_name:
                line = (f"{alg:<18} {mean_g:.2f} ± {se_g:.2f}  "
                        f"{med_g:.2f} {'--':<12} {'--':<8} {'--':<20}")
                write_line(f, line)
            else:
                win = wins[alg]
                win_rate = win / len(all_instances) * 100
                p = p_values[alg]
                star = ''
                if p < 0.01:
                    star = '**'
                elif p < 0.05:
                    star = '*'
                line = (f"{alg:<18} {mean_g:.2f} ± {se_g:.2f}   {med_g:.2f}   "
                        f"{win:<12} {win_rate:.1f}%     {p:.3f} {star}")
                write_line(f, line)

        # ========== 表4‑2：按分组平均gap ==========
        write_line(f, "\n========== 表4‑2 按问题类型与客户规模分组的平均 gap (%) ==========")
        header2 = f"{'分组':<25} {'实例数':<8} "
        for alg in [baseline_name] + [name for _, name in improvements]:
            header2 += f"{alg:<20} "
        write_line(f, header2)

        for group in group_names:
            n_inst = len(group_gaps[baseline_name][group])
            line = f"{group:<25} {n_inst:<8} "
            for alg in [baseline_name] + [name for _, name in improvements]:
                vals = group_gaps[alg][group]
                if vals:
                    mean_g = np.mean(vals)
                    std_g = np.std(vals, ddof=1)
                    line += f"{mean_g:.2f} ± {std_g:.2f}   "
                else:
                    line += f"{'—':<12} "
            write_line(f, line)

        # ========== 表4‑3：各改进算法在每组上的胜/平/负计数 ==========
        write_line(f, "\n========== 表4‑3 各改进算法在每组上的胜出计数（vs 基准） ==========")
        # 初始化分组计数器
        group_wtl = {group: {name: [0,0,0] for _, name in improvements} for group in group_names}
        for inst in all_instances:
            group = inst_categories[inst]
            base_gap = compute_gap(baseline_data[inst]['mean_obj'], baseline_data[inst]['best_obj'])
            for data, name in improvements:
                alg_gap = compute_gap(data[inst]['mean_obj'], baseline_data[inst]['best_obj'])
                if alg_gap < base_gap:
                    group_wtl[group][name][0] += 1
                elif alg_gap == base_gap:
                    group_wtl[group][name][1] += 1
                else:
                    group_wtl[group][name][2] += 1

        header3 = f"{'分组':<25} {'实例数':<8} "
        for _, name in improvements:
            header3 += f"{name:<25} "
        write_line(f, header3)

        for group in group_names:
            n_inst = len(group_gaps[baseline_name][group])
            line = f"{group:<25} {n_inst:<8} "
            for _, name in improvements:
                w, t, l = group_wtl[group][name]
                line += f"{w} / {t} / {l:<7} "
            write_line(f, line)

        # 总计
        line_total = f"{'总计':<25} {len(all_instances):<8} "
        for _, name in improvements:
            w = wins[name]
            t = ties[name]
            l = losses[name]
            line_total += f"{w} / {t} / {l:<7} "
        write_line(f, line_total)

    print(f"\n结果已保存到文件: {args.out}")


if __name__ == '__main__':
    main()