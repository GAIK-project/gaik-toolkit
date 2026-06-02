from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

_BASE = Path(__file__).parent.parent

# 1. Path to CSV
csv_path = _BASE / 'evaluation_results/results.csv'

# 2. Read the data
try:
    df = pd.read_csv(csv_path)
except FileNotFoundError:
    print(f"Error: Could not find {csv_path}. Make sure you are in the task-translation directory.")
    exit()

# 3. Filter for just the AVERAGE rows and select the metric columns
metrics_map = {
    'BLEU': 'BLEU',
    'chrF': 'chrF',
    'TER': 'TER',
    'CosineSim': 'Cosine Similarity'
}

df_avg = df[df['type'] == 'average'].set_index('model')[list(metrics_map.keys())]
df_avg = df_avg.rename(columns=metrics_map)

# 4. Transpose so Metrics are on the X-axis and Models are the bars
df_plot = df_avg.T

# 5. Plotting
ax = df_plot.plot(kind='bar', figsize=(15, 6), width=0.85, colormap='Set2', edgecolor='white')

plt.title('Translation Model Comparison by Evaluation Metric', fontsize=16, fontweight='bold')
plt.ylabel('Score / Error Rate (%)', fontsize=12, fontweight='bold')
plt.xlabel('Evaluation Metric', fontsize=12, fontweight='bold')

plt.xticks(rotation=0, fontsize=11) 

plt.grid(axis='y', linestyle='--', alpha=0.7)
ax.set_axisbelow(True)

plt.legend(title='Translation Models', title_fontsize='11', bbox_to_anchor=(1.01, 1), loc='upper left')

# 6. Add labels on top of the bars
for p in ax.patches:
    height = p.get_height()
    if height > 0.1:  
        ax.annotate(f'{height:.1f}',
                    (p.get_x() + p.get_width() / 2., height),
                    ha='center', va='bottom', fontsize=8, rotation=0, 
                    xytext=(0, 3), textcoords='offset points')

plt.tight_layout()

output_filename = _BASE / 'evaluation_results/translation_metrics_plot.png'

import os
os.makedirs(_BASE / 'evaluation_results', exist_ok=True)

plt.savefig(output_filename, dpi=300, bbox_inches='tight')
print(f"Plot successfully generated and savedI have generated the plot based on the results from the four translation models[cite: 9]!")