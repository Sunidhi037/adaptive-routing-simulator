import csv
import matplotlib.pyplot as plt

def generate_comparison_charts():
    test_ids = []
    d_times = []
    bf_times = []
    
    seen = set()
    with open('evaluation/results.csv', 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            tid = row['test_id']
            if tid not in seen:
                test_ids.append(tid)
                d_times.append(float(row['dijkstra_time_ms']))
                bf_times.append(float(row['bellman_ford_time_ms']))
                seen.add(tid)
                
    # Plotting execution time comparison
    plt.figure(figsize=(8, 5))
    x = range(len(test_ids))
    width = 0.35
    
    plt.bar([p - width/2 for p in x], d_times, width, label='Dijkstra', color='skyblue')
    plt.bar([p + width/2 for p in x], bf_times, width, label='Bellman-Ford', color='salmon')
    
    plt.xlabel('Test Case ID')
    plt.ylabel('Execution Time (ms)')
    plt.title('Algorithm Execution Time Comparison')
    plt.xticks(x, test_ids)
    plt.legend()
    plt.tight_layout()
    
    chart_path = 'execution_time_comparison.png'
    plt.savefig(chart_path)
    print(f"Comparison chart successfully generated and saved to {chart_path}")

if __name__ == "__main__":
    generate_comparison_charts()