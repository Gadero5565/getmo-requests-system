/** @odoo-module **/
import { Component, useState, onWillStart, onMounted } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const Chart = window.Chart;

class RequestsManagerDashboardExtended extends Component {
  static template =
    "extended_dashboard_manager_requests.RequestsManagerDashboardExtended";

  setup() {
    this.state = useState({
      dashboardData: null,
      loading: true,
      error: false,
      activeTab: "recentlyCompleted",
    });
    this.rpc = useService("rpc");
    this.action = useService("action");

    onWillStart(async () => {
      try {
        const data = await this.rpc("/request/dashboard/data", {});
        this.state.dashboardData = data;
        this.state.loading = false;
      } catch (error) {
        this.state.error = true;
        this.state.loading = false;
        console.error("Dashboard loading error:", error);
      }
    });

    onMounted(() => {
      this.renderChart();
      this.renderWorkloadBarChart(); // Changed from renderWorkloadChart()
    });
  }

  renderChart() {
    const canvas = document.getElementById("categoryChart");
    if (!canvas) {
      console.error("Canvas element not found");
      return;
    }

    // Extract data from state
    const categories = this.state.dashboardData.distribution.by_category;

    // Prepare chart data
    const chartData = {
      labels: categories.map((cat) => cat.category_id[1]),
      datasets: [
        {
          data: categories.map((cat) => cat.category_id_count),
          backgroundColor: categories.map((cat) =>
            this.getCategoryColor(cat.category_id[0])
          ), // Use same color function as legend
          borderWidth: 1,
        },
      ],
    };

    try {
      const ctx = canvas.getContext("2d");
      new Chart(ctx, {
        type: "pie",
        data: chartData,
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: function (context) {
                  const label = context.label || "";
                  const value = context.raw || 0;
                  const total = context.dataset.data.reduce((a, b) => a + b, 0);
                  const percentage = Math.round((value / total) * 100);
                  return `${label}: ${value} (${percentage}%)`;
                },
              },
            },
          },
        },
      });
    } catch (error) {
      console.error("Error rendering chart:", error);
    }
  }

renderWorkloadBarChart() {
  const canvas = document.getElementById("workloadBarChart");
  if (!canvas || !this.state.dashboardData?.distribution?.by_category) {
    return;
  }

  const categories = [...this.state.dashboardData.distribution.by_category];
  categories.sort((a, b) => b.category_id_count - a.category_id_count);

  const data = {
    labels: categories.map(cat => cat.category_id[1]),
    datasets: [{
      label: 'Number of Requests',
      data: categories.map(cat => cat.category_id_count),
      backgroundColor: categories.map(cat =>
        this.getCategoryColor(cat.category_id[0])
      ),
      borderWidth: 1
    }]
  };

  try {
    new Chart(canvas.getContext('2d'), {
      type: 'bar',
      data: data,
      options: {
        indexAxis: 'y', // Horizontal bars
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (context) => `${context.parsed.x} requests`
            }
          }
        },
        scales: {
          x: {
            title: {
              display: true,
              text: 'Number of Requests'
            },
            grid: { display: true }
          },
          y: {
            ticks: {
              font: { size: 12 }
            }
          }
        }
      }
    });
  } catch (error) {
    console.error("Error rendering workload chart:", error);
  }
}

  formatNumber(value) {
    return value.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  }

  setActiveTab(tabName) {
    this.state.activeTab = tabName;
  }

  getPriorityClass(priority) {
    const classes = {
      0: "priority-low",
      1: "priority-medium",
      2: "priority-high",
      3: "priority-urgent",
    };
    return classes[priority] || "priority-default";
  }

  getStageColor(stageId) {
    const colorMap = {
      draft: "#95a5a6",
      assigned: "#3498db",
      in_progress: "#f39c12",
      done: "#2ecc71",
      refused: "#e74c3c",
    };
    return colorMap[stageId] || "#7f8c8d";
  }

  getPriorityClass(priority) {
    switch (priority) {
      case "0":
        return "priority-low";
      case "1":
        return "priority-medium";
      case "2":
        return "priority-high";
      case "3":
        return "priority-urgent";
      default:
        return "priority-none";
    }
  }

  getCategoryColor(categoryId) {
    // You can implement a similar mapping as getStageColor
    const colors = [
      "#4361ee",
      "#4895ef",
      "#4cc9f0",
      "#f8961e",
      "#f3722c",
      "#f94144",
    ];
    return colors[categoryId % colors.length];
  }

  formatNumber(num) {
    // Simple number formatting - you can enhance this
    return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  }

  openRequest(recId, modelId) {
    this.action.doAction({
      type: "ir.actions.act_window",
      res_model: modelId,
      res_id: recId,
      views: [[false, "form"]],
      target: "current",
    });
  }
}

registry
  .category("actions")
  .add("requests_manager_dashboard_extended", RequestsManagerDashboardExtended);
