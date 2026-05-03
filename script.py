import os
import sys
import subprocess
import re
import csv
import statistics
import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import datetime

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

def parse_solution_file(sol_file):
    """解析解文件，提取最优成本"""
    if not os.path.exists(sol_file):
        return None
    try:
        with open(sol_file, 'r') as f:
            lines = f.readlines()
            for line in reversed(lines):
                if line.strip().startswith('Cost'):
                    match = re.search(r'Cost\s+(\d+(\.\d+)?)', line)
                    if match:
                        return float(match.group(1))
                match = re.search(r'Cost\s+(\d+(\.\d+)?)', line)
                if match:
                    return float(match.group(1))
            for line in lines:
                if re.match(r'^\d+(\.\d+)?$', line.strip()):
                    return float(line.strip())
    except Exception as e:
        print(f"解析解文件 {sol_file} 时出错: {e}")
    return None

def parse_output(output):
    """解析命令输出，提取结果（不依赖输出中的实例名）"""
    lines = output.strip().split('\n')
    results = {}
    for i, line in enumerate(lines):
        if re.match(r'^\S+\s+[YN]\s+\d+\.?\d*\s+\d+\s+\d+\.?\d*$', line.strip()):
            parts = line.strip().split()
            if len(parts) >= 5:
                results['ok'] = parts[1]
                results['objective'] = float(parts[2])
                results['iterations'] = int(parts[3])
                results['time'] = float(parts[4])
                break
    for line in lines:
        if 'Avg. objective:' in line:
            results['avg_objective'] = float(line.split(':')[1].strip())
        elif 'Avg. iterations:' in line:
            results['avg_iterations'] = float(line.split(':')[1].strip())
        elif 'Avg. run-time:' in line:
            results['avg_runtime'] = float(line.split(':')[1].strip().replace('s', ''))
        elif 'Total not OK:' in line:
            results['total_not_ok'] = int(line.split(':')[1].strip())
    return results

def run_single_test(instance, seed, max_runtime, best_cost=None):
    """运行单个测试实例"""
    cmd = [
        "uv", "run", "pyvrp",
        instance,
        "--seed", str(seed),
        "--max_runtime", str(max_runtime)
    ]
    
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False
        )
        parsed = parse_output(result.stdout)
        if parsed:
            parsed['exit_code'] = result.returncode
            parsed['raw_output'] = result.stdout
            parsed['instance'] = os.path.basename(instance).replace('.vrp', '')
            if best_cost is not None and best_cost > 0 and parsed['ok'] == 'Y':
                try:
                    gap = ((parsed['objective'] - best_cost) / best_cost) * 100
                    parsed['gap_percent'] = gap
                    parsed['best_cost'] = best_cost
                except (ZeroDivisionError, TypeError):
                    parsed['gap_percent'] = None
                    parsed['best_cost'] = best_cost
            else:
                parsed['gap_percent'] = None
                parsed['best_cost'] = best_cost
            return parsed
        else:
            return {
                'instance': os.path.basename(instance).replace('.vrp', ''),
                'ok': 'N',
                'objective': 0,
                'iterations': 0,
                'time': 0,
                'exit_code': result.returncode,
                'raw_output': result.stdout,
                'gap_percent': None,
                'best_cost': best_cost
            }
    except Exception as e:
        print(f"执行出错: {e}")
        return None

def calculate_averages(results_list):
    """计算多个结果的平均值"""
    if not results_list:
        return {}
    objectives = [r['objective'] for r in results_list if r and r['ok'] == 'Y']
    iterations = [r['iterations'] for r in results_list if r and r['ok'] == 'Y']
    times = [r['time'] for r in results_list if r and r['ok'] == 'Y']
    gaps = [r['gap_percent'] for r in results_list if r and r['ok'] == 'Y' and r['gap_percent'] is not None]
    ok_count = sum(1 for r in results_list if r and r['ok'] == 'Y')
    averages = {
        'instance': results_list[0]['instance'],
        'runs': len(results_list),
        'successful_runs': ok_count,
        'success_rate': ok_count / len(results_list) if results_list else 0,
        'best_cost': results_list[0].get('best_cost') if results_list and results_list[0] else None
    }
    if objectives:
        averages['obj_avg'] = statistics.mean(objectives)
    else:
        averages['obj_avg'] = 0
    if iterations:
        averages['iters_avg'] = statistics.mean(iterations)
    else:
        averages['iters_avg'] = 0
    if times:
        averages['time_avg'] = statistics.mean(times)
    else:
        averages['time_avg'] = 0
    if gaps:
        averages['gap_avg'] = statistics.mean(gaps)
        averages['has_gap'] = True
    else:
        averages['gap_avg'] = None
        averages['has_gap'] = False
    return averages

def get_display_path(full_path, base_name):
    """
    从完整路径中提取相对于 'instance' 目录的路径部分（不包含 'instance' 自身），
    并拼接文件名（不含 .vrp）。
    例如：/path/to/instance/CVRP/setA/X.vrp -> CVRP/setA/X
    如果找不到 'instance' 目录，则直接返回 base_name。
    """
    normalized = os.path.normpath(full_path)
    parts = normalized.split(os.sep)
    try:
        idx = parts.index('instance')
        # 取 'instance' 之后的部分，并拼接文件名（不含 .vrp）
        rel_parts = parts[idx+1:-1]  # 去掉文件名的最后一个部分
        if rel_parts:
            display = os.path.join(*rel_parts, base_name)
        else:
            display = base_name
        return display
    except ValueError:
        # 没有找到 'instance' 目录，回退到原名
        return base_name

def find_vrp_files(directories):
    """查找所有vrp文件及对应的解文件，并计算显示名"""
    vrp_info_list = []
    def natural_sort_key(s):
        import re
        return [int(text) if text.isdigit() else text.lower() 
                for text in re.split(r'(\d+)', s)]
    
    for directory in directories:
        if os.path.exists(directory):
            print(f"扫描目录: {directory}")
            current_dir_instances = []
            for root, dirs, files in os.walk(directory):
                dirs.sort(key=natural_sort_key)
                vrp_files = [f for f in files if f.endswith('.vrp')]
                vrp_files.sort(key=natural_sort_key)
                for file in vrp_files:
                    instance_path = os.path.join(root, file)
                    instance_name = file.replace('.vrp', '')
                    # 计算显示名（相对于 instance 目录的路径）
                    display_name = get_display_path(instance_path, instance_name)
                    
                    # 查找解文件
                    sol_file_candidates = [
                        os.path.join(root, f"{instance_name}.sol"),
                        os.path.join(root, f"{instance_name}.sol.txt"),
                        os.path.join(root, f"{instance_name}.opt"),
                        os.path.join(root, f"{instance_name}.optimal")
                    ]
                    best_cost = None
                    for candidate in sol_file_candidates:
                        if os.path.exists(candidate):
                            best_cost = parse_solution_file(candidate)
                            if best_cost is not None:
                                print(f"  ✓ 找到解文件: {os.path.basename(candidate)}, 最优成本: {best_cost}")
                                break
                    if best_cost is None:
                        print(f"  ! 未找到解文件: {display_name}")
                    
                    current_dir_instances.append({
                        'instance_path': instance_path,
                        'instance_name': instance_name,
                        'display_name': display_name,
                        'best_cost': best_cost,
                        'relative_path': os.path.relpath(instance_path, directory)
                    })
            current_dir_instances.sort(key=lambda x: natural_sort_key(x['relative_path']))
            vrp_info_list.extend(current_dir_instances)
            print(f"在目录 {directory} 中找到 {len(current_dir_instances)} 个实例文件")
        else:
            print(f"警告: 目录不存在: {directory}")
    return vrp_info_list

def run_multi_seed_tests_parallel(vrp_info_list, seeds, max_runtime, detailed_csv, summary_csv, workers=80):
    """并行运行多种子测试"""
    print(f"使用种子: {seeds}")
    print(f"最大运行时间: {max_runtime}秒")
    print(f"测试实例: {len(vrp_info_list)}个")
    print(f"详细结果CSV: {detailed_csv}")
    print(f"汇总结果CSV: {summary_csv}")
    print(f"并行线程数: {workers}")

    instances_with_sol = sum(1 for info in vrp_info_list if info['best_cost'] is not None)
    print(f"包含最优解文件的实例: {instances_with_sol}/{len(vrp_info_list)}")

    # 建立 instance_name -> display_name 映射
    display_map = {info['instance_name']: info['display_name'] for info in vrp_info_list}

    # 构建所有任务列表
    tasks = []
    for vrp_info in vrp_info_list:
        instance_path = vrp_info['instance_path']
        instance_name = vrp_info['instance_name']
        best_cost = vrp_info['best_cost']
        for seed in seeds:
            tasks.append((instance_name, instance_path, seed, max_runtime, best_cost))

    total_tasks = len(tasks)
    print(f"总任务数: {total_tasks} (实例数 × 种子数)")

    results = []
    progress_lock = threading.Lock()
    completed_count = 0

    def run_task(instance_name, instance_path, seed, max_runtime, best_cost):
        result = run_single_test(instance_path, seed, max_runtime, best_cost)
        return (instance_name, seed, result)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_task = {
            executor.submit(run_task, name, path, seed, runtime, cost): (name, seed)
            for name, path, seed, runtime, cost in tasks
        }

        if HAS_TQDM:
            pbar = tqdm(total=total_tasks, desc="运行任务")
        else:
            pbar = None

        for future in as_completed(future_to_task):
            name, seed = future_to_task[future]
            try:
                result_tuple = future.result()
                results.append(result_tuple)
            except Exception as e:
                print(f"任务 {name} 种子 {seed} 异常: {e}")
                results.append((name, seed, None))
            finally:
                with progress_lock:
                    completed_count += 1
                    if pbar:
                        pbar.update(1)
                    else:
                        if completed_count % 10 == 0 or completed_count == total_tasks:
                            print(f"进度: {completed_count}/{total_tasks} ({completed_count/total_tasks*100:.1f}%)")

        if pbar:
            pbar.close()

    # 按实例分组结果
    instance_results = defaultdict(list)
    for name, seed, res in results:
        if res is not None:
            res['seed'] = seed
            instance_results[name].append(res)

    # 准备详细结果行（使用 display_name）
    detail_rows = []
    for instance_name, res_list in instance_results.items():
        display_name = display_map[instance_name]
        for res in res_list:
            row = [
                display_name,
                res['seed'],
                res['objective'],
                res.get('best_cost', 'N/A'),
                f"{res['gap_percent']:.3f}" if res['gap_percent'] is not None else 'N/A',
                res['iterations'],
                res['time'],
                res['ok'],
                res['exit_code']
            ]
            detail_rows.append(row)

    # 写入详细CSV
    with open(detailed_csv, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Instance', 'Seed', 'Obj.', 'Best Obj.', 'GAP(%)', 'Iters', 'Time (s)', 'OK', 'Exit Code'])
        writer.writerows(detail_rows)

    # 计算汇总，按 display_name 字典序排序
    summary_rows = []
    # 按 display_name 排序实例
    sorted_instances = sorted(instance_results.keys(), key=lambda ins: display_map[ins])
    for instance_name in sorted_instances:
        res_list = instance_results[instance_name]
        best_cost = res_list[0].get('best_cost') if res_list else None
        avg = calculate_averages(res_list)
        avg['best_cost'] = best_cost
        display_name = display_map[instance_name]
        row = [
            display_name,
            f"{best_cost:.0f}" if best_cost is not None else 'N/A',
            avg['runs'],
            avg['successful_runs'],
            f"{avg['success_rate']:.3f}",
            f"{avg['obj_avg']:.2f}",
            f"{avg['gap_avg']:.3f}" if avg.get('has_gap') and avg['gap_avg'] is not None else 'N/A',
            f"{avg['iters_avg']:.1f}",
            f"{avg['time_avg']:.2f}"
        ]
        summary_rows.append(row)

    with open(summary_csv, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Instance', 'Best Obj.', 'Runs', 'Successful', 'Success Rate',
                         'Obj Avg', 'GAP Avg(%)', 'Iters Avg', 'Time Avg'])
        writer.writerows(summary_rows)

    print(f"\n{'='*80}")
    print("测试完成！")
    print(f"详细结果: {detailed_csv}")
    print(f"汇总结果: {summary_csv}")

    # 显示汇总表格
    if summary_rows:
        print("\n汇总表格:")
        print("-" * 110)
        print(f"{'Instance':<30} {'Best':<10} {'Runs':<6} {'Success':<8} {'Obj Avg':<10} {'GAP Avg(%)':<12} {'Iters Avg':<10} {'Time Avg':<10}")
        print("-" * 110)
        for row in summary_rows:
            print(f"{row[0]:<30} {row[1]:<10} "
                  f"{row[2]:<6} "
                  f"{row[3]}/{row[2]:<7} "
                  f"{row[5]:<10} "
                  f"{row[6]:<12} "
                  f"{row[7]:<10} "
                  f"{row[8]:<10}")
    else:
        print("无有效结果")

def main():
    parser = argparse.ArgumentParser(description='批量运行VRP测试（并行版本）')
    parser.add_argument('--max_runtime', type=int, default=60, help='最大运行时间（秒）')
    parser.add_argument('--dir', action='append', help='实例目录（可多次使用）', default=[])
    parser.add_argument('--seeds', type=str, default='42', help='种子列表，用逗号分隔')
    parser.add_argument('--detailed_csv', default='detailed_result.csv', help='详细结果CSV文件名（基础名，最终会添加时间戳并放入vrp_logs目录）')
    parser.add_argument('--summary_csv', default='summary_result.csv', help='汇总结果CSV文件名（基础名，最终会添加时间戳并放入vrp_logs目录）')
    parser.add_argument('--workers', type=int, default=80, help='并行线程数')

    args = parser.parse_args()

    if not args.dir:
        args.dir = ['instance/CVRP', 'instance/VRPTW']
        print("未指定 --dir，使用默认目录: instance/CVRP, instance/VRPTW")

    seeds = [int(seed.strip()) for seed in args.seeds.split(',')]

    vrp_info_list = find_vrp_files(args.dir)

    if not vrp_info_list:
        print("错误: 没有找到任何实例文件")
        sys.exit(1)

    print("\n找到的实例文件:")
    for i, info in enumerate(vrp_info_list, 1):
        best_str = f"最优成本: {info['best_cost']}" if info['best_cost'] is not None else "无解文件"
        print(f"{i:3d}. {info['display_name']:<40} ({best_str})")

    total_tasks = len(vrp_info_list) * len(seeds)
    print(f"\n将测试 {len(vrp_info_list)} 个实例，使用 {len(seeds)} 个种子，共 {total_tasks} 个任务")
    response = input("是否继续? (y/n): ")
    if response.lower() != 'y':
        print("测试取消")
        sys.exit(0)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")

    detailed_basename = os.path.basename(args.detailed_csv)
    detailed_name, detailed_ext = os.path.splitext(detailed_basename)
    detailed_csv_with_ts = f"{detailed_name}_{timestamp}{detailed_ext}"

    summary_basename = os.path.basename(args.summary_csv)
    summary_name, summary_ext = os.path.splitext(summary_basename)
    summary_csv_with_ts = f"{summary_name}_{timestamp}{summary_ext}"

    log_dir = "vrp_logs"
    os.makedirs(log_dir, exist_ok=True)

    detailed_csv_path = os.path.join(log_dir, detailed_csv_with_ts)
    summary_csv_path = os.path.join(log_dir, summary_csv_with_ts)

    run_multi_seed_tests_parallel(
        vrp_info_list=vrp_info_list,
        seeds=seeds,
        max_runtime=args.max_runtime,
        detailed_csv=detailed_csv_path,
        summary_csv=summary_csv_path,
        workers=args.workers
    )

if __name__ == "__main__":
    main()