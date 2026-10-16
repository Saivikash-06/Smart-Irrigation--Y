/**
 * GreenPulse – Live Moisture Trend Chart
 * Powered by Chart.js with threshold indicator and live telemetry ingestion.
 */

class MoistureChartManager {
  constructor(canvasId) {
    this.canvas = document.getElementById(canvasId);
    this.chart = null;
    this.threshold = 30.0;
    this.maxPoints = 25;
  }

  init(initialData = [], threshold = 30.0) {
    if (!this.canvas) return;
    this.threshold = threshold;

    const ctx = this.canvas.getContext('2d');

    // Create subtle emerald gradient fill
    const gradient = ctx.createLinearGradient(0, 0, 0, 300);
    gradient.addColorStop(0, 'rgba(34, 197, 94, 0.45)');
    gradient.addColorStop(1, 'rgba(34, 197, 94, 0.02)');

    const labels = initialData.map(d => this.formatTime(d.timestamp));
    const moistureValues = initialData.map(d => d.moisture);

    this.chart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [
          {
            label: 'Soil Moisture (%)',
            data: moistureValues,
            borderColor: '#16a34a',
            borderWidth: 2.5,
            backgroundColor: gradient,
            fill: true,
            tension: 0.35,
            pointRadius: 3,
            pointHoverRadius: 6,
            pointBackgroundColor: '#15803d',
          },
          {
            label: `Irrigation Threshold (${this.threshold}%)`,
            data: new Array(labels.length).fill(this.threshold),
            borderColor: '#ef4444',
            borderWidth: 2,
            borderDash: [6, 4],
            fill: false,
            pointRadius: 0,
            pointHoverRadius: 0,
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: {
          duration: 400,
        },
        interaction: {
          intersect: false,
          mode: 'index',
        },
        plugins: {
          legend: {
            position: 'top',
            labels: {
              usePointStyle: true,
              boxWidth: 8,
              font: {
                family: 'Inter',
                size: 12,
                weight: '500',
              }
            }
          },
          tooltip: {
            backgroundColor: '#0f172a',
            titleFont: { family: 'Inter', size: 12 },
            bodyFont: { family: 'Inter', size: 13, weight: 'bold' },
            padding: 10,
            cornerRadius: 8,
            callbacks: {
              label: function(context) {
                return `${context.dataset.label}: ${context.parsed.y}%`;
              }
            }
          }
        },
        scales: {
          y: {
            min: 0,
            max: 100,
            ticks: {
              stepSize: 20,
              callback: value => `${value}%`,
              font: { family: 'Inter', size: 11 },
              color: '#64748b',
            },
            grid: {
              color: '#f1f5f9',
            }
          },
          x: {
            ticks: {
              font: { family: 'Inter', size: 11 },
              color: '#64748b',
              maxRotation: 0,
              autoSkip: true,
              maxTicksLimit: 7,
            },
            grid: {
              display: false,
            }
          }
        }
      }
    });
  }

  addReading(timestamp, moisture) {
    if (!this.chart) return;

    const timeLabel = this.formatTime(timestamp);
    this.chart.data.labels.push(timeLabel);
    this.chart.data.datasets[0].data.push(moisture);
    this.chart.data.datasets[1].data.push(this.threshold);

    // Keep dataset bounded to prevent memory issues
    if (this.chart.data.labels.length > this.maxPoints) {
      this.chart.data.labels.shift();
      this.chart.data.datasets[0].data.shift();
      this.chart.data.datasets[1].data.shift();
    }

    this.chart.update('none'); // Update without full reload animation for smooth 60fps feel
  }

  updateThreshold(newThreshold) {
    this.threshold = newThreshold;
    if (this.chart) {
      this.chart.data.datasets[1].label = `Irrigation Threshold (${newThreshold}%)`;
      this.chart.data.datasets[1].data = new Array(this.chart.data.labels.length).fill(newThreshold);
      this.chart.update();
    }
  }

  formatTime(isoString) {
    try {
      const d = new Date(isoString);
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch (_) {
      return '';
    }
  }
}

window.MoistureChart = MoistureChartManager;
