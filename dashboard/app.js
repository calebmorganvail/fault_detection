var WINDOW_SIZE = 30;
var WARNING_THRESHOLD = 2;
var MAX_POINTS = 100;
var POLL_INTERVAL = 1000;

var SENSOR_COLOR = "#ca9ee6";
var BASELINE_COLOR = "#eebebe";
var AXIS_COLOR = "#6c6f85";
var GRID_COLOR = "#ccd0da";

var activeTab = "simulation";

// --- shared math ---------------------------------------------------------

function toFahrenheit(tempC) {
  return (tempC * 9) / 5 + 32;
}

function getAbsoluteDivergence(tempAf, tempBf) {
  return Math.abs(tempAf - tempBf);
}

function getSlidingWindowFault(divergences, threshold) {
  var window = divergences.slice(-WINDOW_SIZE);

  if (window.length === 0) return { average: 0, isFault: false };

  var sum = 0;
  for (var i = 0; i < window.length; i++) {
    sum += window[i];
  }
  var average = sum / window.length;

  return { average: average, isFault: average > threshold };
}

function getFaultLevel(divergence, fault) {
  if (fault.isFault) return "fault";
  if (divergence > WARNING_THRESHOLD) return "warning";
  return "online";
}

function getThreshold() {
  return parseFloat(document.getElementById("fault-threshold").value) || 5;
}

function formatLabel(timestamp) {
  return timestamp.slice(11, 19);
}

// --- charts --------------------------------------------------------------

var simChart = new Chart(document.getElementById("sim-chart"), {
  type: "bar",
  data: {
    labels: ["DHT22 Sensor Reading", "Simulated Temperature"],
    datasets: [
      {
        data: [0, 0],
        backgroundColor: [SENSOR_COLOR, BASELINE_COLOR],
        borderColor: [SENSOR_COLOR, BASELINE_COLOR],
        borderWidth: 1,
        borderRadius: 4,
      },
    ],
  },
  options: {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    scales: {
      y: {
        title: { display: true, text: "°F", color: AXIS_COLOR },
        ticks: { color: AXIS_COLOR },
        grid: { color: GRID_COLOR },
      },
      x: {
        ticks: { color: AXIS_COLOR },
        grid: { color: GRID_COLOR },
      },
    },
    plugins: { legend: { display: false } },
  },
});

// The live chart is the scrolling line chart from v1, restyled to match
// the v2 palette.
var liveChart = new Chart(document.getElementById("live-chart"), {
  type: "line",
  data: {
    labels: [],
    datasets: [
      {
        label: "DHT22 Sensor (A)",
        data: [],
        borderColor: SENSOR_COLOR,
        borderWidth: 2,
        pointRadius: 0,
        tension: 0.3,
      },
      {
        label: "DHT22 Sensor (B)",
        data: [],
        borderColor: BASELINE_COLOR,
        borderWidth: 2,
        pointRadius: 0,
        tension: 0.3,
      },
    ],
  },
  options: {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    scales: {
      y: {
        title: { display: true, text: "°F", color: AXIS_COLOR },
        ticks: { color: AXIS_COLOR },
        grid: { color: GRID_COLOR },
      },
      x: {
        ticks: { color: AXIS_COLOR, maxTicksLimit: 8 },
        grid: { color: GRID_COLOR },
      },
    },
    plugins: { legend: { labels: { color: AXIS_COLOR } } },
  },
});

// --- tabs ----------------------------------------------------------------

function setTab(name) {
  activeTab = name;
  document.body.className = name === "live" ? "tab-live" : "tab-simulation";

  var buttons = document.querySelectorAll(".tab");
  for (var i = 0; i < buttons.length; i++) {
    buttons[i].classList.toggle("active", buttons[i].dataset.tab === name);
  }

  // The hidden canvas has no size, so tell Chart.js to measure again.
  if (name === "live") {
    liveChart.resize();
  } else {
    simChart.resize();
  }

  update();
}

var tabButtons = document.querySelectorAll(".tab");
for (var i = 0; i < tabButtons.length; i++) {
  tabButtons[i].addEventListener("click", function () {
    setTab(this.dataset.tab);
  });
}

// --- simulated temperature input -----------------------------------------

document.getElementById("sim-temp").addEventListener("change", function () {
  var tempF = parseFloat(this.value);
  var tempC = ((tempF - 32) * 5) / 9;
  fetch("/api/simulated-temp", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ temp_c: tempC }),
  });
});

// --- simulation tab ------------------------------------------------------

function updateSimulationTab() {
  fetch("/api/simulation?limit=" + WINDOW_SIZE)
    .then(function (res) {
      return res.json();
    })
    .then(function (rows) {
      if (rows.length === 0) return;

      var divergences = rows.map(function (row) {
        return getAbsoluteDivergence(
          toFahrenheit(row.sensor_temp_c),
          toFahrenheit(row.simulated_temp_c),
        );
      });

      var latest = rows[rows.length - 1];
      var sensorF = toFahrenheit(latest.sensor_temp_c);
      var baselineF = toFahrenheit(latest.simulated_temp_c);
      var divergence = divergences[divergences.length - 1];
      var fault = getSlidingWindowFault(divergences, getThreshold());

      simChart.data.datasets[0].data = [sensorF, baselineF];
      simChart.update();

      document.getElementById("timestamp").textContent =
        "Timestamp: " + latest.timestamp;
      document.getElementById("sim-sensor-temp").textContent =
        sensorF.toFixed(1) + "°F";
      document.getElementById("sim-baseline-temp").textContent =
        baselineF.toFixed(1) + "°F";
      document.getElementById("fault-divergence").textContent =
        divergence.toFixed(1) + "°F";
      document.getElementById("dot-fault").className =
        "status-dot " + getFaultLevel(divergence, fault);
    });
}

// --- multiple live sensors tab -------------------------------------------

function updateLiveTab() {
  fetch("/api/sensors?limit=" + MAX_POINTS)
    .then(function (res) {
      return res.json();
    })
    .then(function (rows) {
      if (rows.length === 0) return;

      // Every row is a pair the server already matched up, so A and B
      // always share the same timestamp.
      liveChart.data.labels = rows.map(function (row) {
        return formatLabel(row.timestamp);
      });
      liveChart.data.datasets[0].data = rows.map(function (row) {
        return toFahrenheit(row.temp_a_c);
      });
      liveChart.data.datasets[1].data = rows.map(function (row) {
        return toFahrenheit(row.temp_b_c);
      });
      liveChart.update();

      var divergences = rows.map(function (row) {
        return getAbsoluteDivergence(
          toFahrenheit(row.temp_a_c),
          toFahrenheit(row.temp_b_c),
        );
      });

      var latest = rows[rows.length - 1];
      var tempAf = toFahrenheit(latest.temp_a_c);
      var tempBf = toFahrenheit(latest.temp_b_c);
      var divergence = divergences[divergences.length - 1];
      var fault = getSlidingWindowFault(divergences, getThreshold());

      document.getElementById("timestamp").textContent =
        "Timestamp: " + latest.timestamp;
      document.getElementById("live-temp-a").textContent =
        tempAf.toFixed(1) + "°F";
      document.getElementById("live-temp-b").textContent =
        tempBf.toFixed(1) + "°F";
      document.getElementById("fault-divergence").textContent =
        divergence.toFixed(1) + "°F";
      document.getElementById("dot-fault").className =
        "status-dot " + getFaultLevel(divergence, fault);
    });
}

// --- connected sensor dots -----------------------------------------------

function updateStatus() {
  fetch("/api/status")
    .then(function (res) {
      return res.json();
    })
    .then(function (status) {
      setDot("dot-sim", status.sensors.A.online);
      setDot("dot-a", status.sensors.A.online);
      setDot("dot-b", status.sensors.B.online);
    });
}

function setDot(id, online) {
  document.getElementById(id).className =
    "status-dot" + (online ? " online" : "");
}

// --- polling -------------------------------------------------------------

function update() {
  updateStatus();
  if (activeTab === "live") {
    updateLiveTab();
  } else {
    updateSimulationTab();
  }
}

update();
setInterval(update, POLL_INTERVAL);
