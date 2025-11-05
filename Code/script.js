let ctx = document.getElementById('tempChart').getContext('2d');
let chart = new Chart(ctx, {
  type: 'line',
  data: { labels: [], datasets: [{ label: 'Temperature (°C)', data: [] }] },
  options: { responsive: true }
});

async function fetchData() {
  const res = await fetch('/get_data');
  const data = await res.json();
  chart.data.labels = data.map(d => d[2]);
  chart.data.datasets[0].data = data.map(d => d[0]);
  chart.update();
}

setInterval(fetchData, 5000);
fetchData();

document.getElementById('searchForm').addEventListener('submit', async e => {
  e.preventDefault();
  const formData = new FormData(e.target);
  const res = await fetch('/search', { method: 'POST', body: formData });
  const data = await res.json();
  document.getElementById('searchResults').innerHTML =
    `<h3>Search Results</h3><pre>${JSON.stringify(data, null, 2)}</pre>`;
});
