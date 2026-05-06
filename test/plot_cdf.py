#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from collections import defaultdict

def load_algorithm_results(csv_file: str):
    df = pd.read_csv(csv_file)
    required = ['Instance', 'Seed', 'Obj.', 'Best Obj.']
    for col in required:
        if col not in df.columns:
            raise ValueError(f"{csv_file} 缺少列 {col}")
    data = {}
    for inst in df['Instance'].unique():
        sub = df[df['Instance'] == inst]
        best = sub['Best Obj.'].iloc[0]
        mean_obj = sub['Obj.'].mean()
        data[inst] = {'mean_obj': mean_obj, 'best_obj': best}
    return data

def compute_gap(mean_obj, best_obj):
    return (mean_obj - best_obj) / best_obj * 100.0

def plot_cdf(delta_gaps_dict, output_file, x_range=(-0.4, 0.3)):
    """
    delta_gaps_dict: dict {alg_name: numpy array of delta_gap values}
    output_file: 输出图片路径
    x_range: 横轴显示范围，默认(-0.4, 0.3)
    """
    plt.figure(figsize=(10, 6))
    # 使用更鲜明的颜色：tab10 已经不错，但可以加线型区分，这里用Set1
    # 若算法数量超过9，自动循环
    colors = plt.cm.Set1(np.linspace(0, 1, len(delta_gaps_dict)))
    # 辅助线型列表（用于增加区分度）
    linestyles = ['-', '--', '-.', ':', (0, (3,1,1,1))] * (len(delta_gaps_dict)//4 + 1)
    
    # 用于记录标签位置（x=y=0附近）
    label_positions = []  # (y, offset_direction)  direction: 'up', 'down', 'left', 'right'
    
    for idx, (alg_name, deltas) in enumerate(delta_gaps_dict.items()):
        deltas_sorted = np.sort(deltas)
        y = np.arange(1, len(deltas_sorted) + 1) / len(deltas_sorted)
        # 绘制阶梯曲线
        plt.step(deltas_sorted, y, where='post',
                 label=alg_name, linewidth=2.5,
                 color=colors[idx], linestyle=linestyles[idx % len(linestyles)])
        
        win_rate = np.mean(deltas < 0) * 100
        # 找到 Δgap=0 对应的累积比例（左连续）
        idx_zero = np.searchsorted(deltas_sorted, 0, side='right') - 1
        y0 = y[idx_zero] if idx_zero >= 0 else 0.0
        
        # 在曲线上的点标记一个圆点
        plt.plot(0, y0, 'o', color=colors[idx], markersize=6)
        
        # ---- 智能偏移避免重叠 ----
        # 默认偏移
        offset_x, offset_y = 5, 5
        # 检查与已有标签的冲突（x坐标均为0或接近0，y坐标相近）
        conflict = False
        for other_y, other_dir in label_positions:
            if abs(y0 - other_y) < 0.08:
                conflict = True
                break
        if conflict:
            # 根据已存在的偏移方向进行分配
            up_count = sum(1 for _, d in label_positions if d == 'up')
            down_count = sum(1 for _, d in label_positions if d == 'down')
            left_count = sum(1 for _, d in label_positions if d == 'left')
            right_count = sum(1 for _, d in label_positions if d == 'right')
            # 优先分配使用较少的方位
            if up_count <= down_count and up_count <= left_count and up_count <= right_count:
                offset_y = 15
                direction = 'up'
            elif down_count <= up_count and down_count <= left_count and down_count <= right_count:
                offset_y = -15
                direction = 'down'
            elif left_count <= right_count:
                offset_x = -20
                direction = 'left'
            else:
                offset_x = 20
                direction = 'right'
        else:
            # 无冲突时默认向上偏移
            offset_y = 10
            direction = 'up'
        
        label_positions.append((y0, direction))
        
        plt.annotate(f"{win_rate:.1f}%", xy=(0, y0), xytext=(offset_x, offset_y),
                     textcoords='offset points', fontsize=9,
                     color=colors[idx], weight='bold',
                     bbox=dict(boxstyle='round,pad=0.2', fc='white', alpha=0.7))
    
    # 垂直参考线
    plt.axvline(x=0, linestyle='--', color='gray', alpha=0.7, linewidth=1)
    plt.xlabel(r'$\Delta$ gap (%) = gap$_{\text{improved}}$ - gap$_{\text{baseline}}$', fontsize=12)
    plt.ylabel('Cumulative proportion of instances', fontsize=12)
    plt.title('Cumulative distribution of gap improvement', fontsize=14)
    plt.grid(True, alpha=0.3, linestyle=':')
    plt.xlim(x_range[0], x_range[1])
    plt.ylim(0, 1.05)
    plt.legend(loc='lower right', fontsize=10)
    plt.tight_layout()
    plt.savefig(output_file, dpi=300)
    plt.close()
    print(f"CDF曲线已保存至: {output_file}")

def main():
    parser = argparse.ArgumentParser(description='绘制CDF曲线，固定横轴范围[-0.4,0.3]')
    parser.add_argument('--baseline', required=True)
    parser.add_argument('--improvements', nargs='+', required=True)
    parser.add_argument('--names', nargs='+', default=None)
    parser.add_argument('--output', default='cdf_curves.png')
    parser.add_argument('--xmin', type=float, default=-0.3, help='横轴最小值')
    parser.add_argument('--xmax', type=float, default=0.3, help='横轴最大值')
    args = parser.parse_args()

    baseline_data = load_algorithm_results(args.baseline)
    baseline_instances = set(baseline_data.keys())
    delta_gaps = {}
    summary_stats = []

    for i, imp_file in enumerate(args.improvements):
        imp_data = load_algorithm_results(imp_file)
        common_instances = baseline_instances.intersection(set(imp_data.keys()))
        if not common_instances:
            raise ValueError(f"基准与{imp_file}无公共实例")
        alg_name = args.names[i] if args.names and i < len(args.names) else imp_file.split('/')[-1].replace('.csv', '')
        deltas = []
        for inst in common_instances:
            best_obj = baseline_data[inst]['best_obj']
            base_gap = compute_gap(baseline_data[inst]['mean_obj'], best_obj)
            imp_gap = compute_gap(imp_data[inst]['mean_obj'], best_obj)
            deltas.append(imp_gap - base_gap)
        deltas_arr = np.array(deltas)
        delta_gaps[alg_name] = deltas_arr
        
        mean_d = np.mean(deltas_arr)
        median_d = np.median(deltas_arr)
        std_d = np.std(deltas_arr)
        q25 = np.percentile(deltas_arr, 25)
        q75 = np.percentile(deltas_arr, 75)
        win_rate = np.mean(deltas_arr < 0) * 100
        summary_stats.append((alg_name, len(deltas), mean_d, median_d, std_d, q25, q75, win_rate))
        print(f"算法 {alg_name}: 有效实例数={len(deltas)}, 胜率={win_rate:.1f}%")

    print("\n========== Δgap 描述性统计 ==========")
    print(f"{'算法':<18} {'均值(%)':<10} {'中位数(%)':<12} {'标准差(%)':<12} {'25%分位(%)':<12} {'75%分位(%)':<12} {'胜率(%)':<10}")
    for stat in summary_stats:
        alg, n, mean_d, med_d, std_d, q25, q75, wr = stat
        print(f"{alg:<18} {mean_d:>8.3f}   {med_d:>8.3f}   {std_d:>8.3f}   {q25:>8.3f}   {q75:>8.3f}   {wr:>8.1f}")

    plot_cdf(delta_gaps, args.output, x_range=(args.xmin, args.xmax))

if __name__ == '__main__':
    main()