// Client State Management
const state = {
    activeTab: 'dashboard',
    // Live inputs on Calculator
    calculatorInputs: {
        transport: { car_km: 0, bus_km: 0, flight_km: 0 },
        energy: { grid_kwh: 0, green_kwh: 0 },
        diet: 'balanced',
        waste: { landfill_kg: 0, recycled_kg: 0 }
    },
    latestCalculation: null,
    history: [],
    goals: [],
    badges: [],
    offsetSimulator: {
        trees: 0,
        credits: 0,
        methane: 0
    }
};

// Global Chart References
let historyChart = null;
let donutChart = null;

// Initialize app when DOM is fully loaded
document.addEventListener('DOMContentLoaded', () => {
    initApp();
});

function initApp() {
    // 1. Set current date in header
    const options = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
    document.getElementById('current-date').textContent = new Date().toLocaleDateString('en-US', options);

    // 2. Setup SPA Tab Switches
    setupTabNavigation();

    // 3. Bind Sliders and Form Inputs
    setupCalculatorListeners();
    setupOffsetListeners();

    // 4. Fetch initial API data from FastAPI backend
    refreshData();

    // 5. Setup AI Coach sending
    setupChatListeners();

    // 6. Polling Developer Carbon Footprint Metrics
    fetchDevMetrics();
    setInterval(fetchDevMetrics, 10000); // refresh dev metrics every 10 seconds
}

// Tab Switches Routing
function setupTabNavigation() {
    const navItems = document.querySelectorAll('.nav-item');
    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            const btn = e.currentTarget;
            const targetTab = btn.getAttribute('data-tab');
            
            // Toggle sidebar active button
            navItems.forEach(n => n.classList.remove('active'));
            btn.classList.add('active');

            // Switch content panel
            document.querySelectorAll('.tab-panel').forEach(panel => {
                panel.classList.remove('active');
            });
            document.getElementById(`tab-${targetTab}`).classList.add('active');

            state.activeTab = targetTab;
            
            // Reload context if switching to Dashboard to render charts correctly
            if (targetTab === 'dashboard') {
                setTimeout(renderCharts, 50);
            }
        });
    });
}

// Calculator input bindings
function setupCalculatorListeners() {
    // Inputs & Sliders mappings
    const mappings = [
        { id: 'car', category: 'transport', field: 'car_km', unit: 'km' },
        { id: 'bus', category: 'transport', field: 'bus_km', unit: 'km' },
        { id: 'flight', category: 'transport', field: 'flight_km', unit: 'km' },
        { id: 'grid', category: 'energy', field: 'grid_kwh', unit: 'kWh' },
        { id: 'green', category: 'energy', field: 'green_kwh', unit: 'kWh' },
        { id: 'landfill', category: 'waste', field: 'landfill_kg', unit: 'kg' },
        { id: 'recycled', category: 'waste', field: 'recycled_kg', unit: 'kg' }
    ];

    mappings.forEach(item => {
        const slider = document.getElementById(`slider-${item.id}`);
        const labelVal = document.getElementById(`val-${item.id}`);
        
        slider.addEventListener('input', (e) => {
            const val = parseFloat(e.target.value);
            labelVal.textContent = `${val} ${item.unit}`;
            
            // Update state
            state.calculatorInputs[item.category][item.field] = val;
            
            // Recalculate Live Score
            recalculateLiveScore();
        });
    });

    // Diet options (radio equivalents)
    const dietOptions = document.querySelectorAll('.diet-option');
    dietOptions.forEach(opt => {
        opt.addEventListener('click', () => {
            dietOptions.forEach(o => o.classList.remove('active'));
            opt.classList.add('active');
            
            const radio = opt.querySelector('input[type="radio"]');
            radio.checked = true;
            state.calculatorInputs.diet = radio.value;
            
            recalculateLiveScore();
        });
    });

    // Save calculation button
    document.getElementById('btn-save-calculation').addEventListener('click', saveCalculation);
}

// Offset simulator bindings
function setupOffsetListeners() {
    const offsets = [
        { id: 'trees', label: 'val-sim-trees', suffix: 'Trees' },
        { id: 'credits', label: 'val-sim-credits', suffix: 'kWh' },
        { id: 'methane', label: 'val-sim-methane', suffix: 'kg' }
    ];

    offsets.forEach(item => {
        const slider = document.getElementById(`slider-sim-${item.id}`);
        const label = document.getElementById(item.label);
        
        slider.addEventListener('input', (e) => {
            const val = parseInt(e.target.value);
            label.textContent = `${val} ${item.suffix}`;
            
            state.offsetSimulator[item.id] = val;
            updateOffsetLedger();
        });
    });
}

// Calculate live carbon footprints on front-end for immediate visual responsiveness
function recalculateLiveScore() {
    // Math equivalents matching backend factors (carbon_utils.py)
    const transport = state.calculatorInputs.transport;
    const transportCO2 = (transport.car_km * 0.20) + (transport.bus_km * 0.04) + (transport.flight_km * 0.15);

    const energy = state.calculatorInputs.energy;
    const energyCO2 = (energy.grid_kwh * 0.45) + (energy.green_kwh * 0.02);

    const dietFactors = { meat_heavy: 2.5, balanced: 1.8, vegetarian: 1.2, vegan: 0.8 };
    const dietCO2 = (dietFactors[state.calculatorInputs.diet] || 1.8) * 7; // weekly

    const waste = state.calculatorInputs.waste;
    const wasteCO2 = (waste.landfill_kg * 0.50) + (waste.recycled_kg * 0.05);

    const liveTotal = transportCO2 + energyCO2 + dietCO2 + wasteCO2;
    
    // Update score text
    document.getElementById('calc-live-total').textContent = liveTotal.toFixed(2);
    
    // Update live gauge percentage bar (cap at 150 kg max for safety visual)
    const percentage = Math.min((liveTotal / 120) * 100, 100);
    document.getElementById('calc-gauge-bar').style.width = `${percentage}%`;

    // Sync current values to offset ledger gross
    updateOffsetLedger(liveTotal);
}

// Update Net Zero Offset ledger
function updateOffsetLedger(forcedGross = null) {
    // Use last calculated score or live score
    let gross = 0.00;
    if (forcedGross !== null) {
        gross = forcedGross;
    } else if (state.latestCalculation) {
        gross = state.latestCalculation.total;
    } else {
        // Fallback to reading from calculator score UI
        gross = parseFloat(document.getElementById('calc-live-total').textContent) || 0.0;
    }

    // Offset Math:
    // Tree: 22kg/year -> 0.42 kg/week
    const treesWeeklyOffset = state.offsetSimulator.trees * 0.42;
    // Credit: green grid energy offseting standard grid (0.45 kg/kWh saved)
    const creditsWeeklyOffset = state.offsetSimulator.credits * 0.45;
    // Methane Capture: compost/digesters offset (0.50 kg CO2 / kg waste saved)
    const methaneWeeklyOffset = state.offsetSimulator.methane * 0.50;

    const totalOffset = treesWeeklyOffset + creditsWeeklyOffset + methaneWeeklyOffset;
    const net = Math.max(gross - totalOffset, 0);

    document.getElementById('ledger-gross').textContent = `${gross.toFixed(2)} kg`;
    document.getElementById('ledger-offset').textContent = `${totalOffset.toFixed(2)} kg`;
    document.getElementById('ledger-net').textContent = `${net.toFixed(2)} kg`;

    const indicator = document.getElementById('neutrality-indicator');
    const statusText = document.getElementById('neutrality-status');

    if (net <= 0.01 && gross > 0) {
        indicator.classList.add('neutral');
        statusText.textContent = "Carbon Neutral! 🎉";
        statusText.className = "neutrality-text text-green";
    } else {
        indicator.classList.remove('neutral');
        statusText.textContent = "CO₂ Positive";
        statusText.className = "neutrality-text text-red";
    }
}

// Fetch all states from API
async function refreshData() {
    try {
        // Fetch History
        const histRes = await fetch('/api/history');
        state.history = await histRes.json();

        if (state.history.length > 0) {
            state.latestCalculation = state.history[0];
            
            // Sync values to Dashboard metrics
            document.getElementById('dash-total-co2').innerHTML = `${state.latestCalculation.total.toFixed(2)} <span class="unit">kg CO₂</span>`;
            document.getElementById('dash-trees').innerHTML = `${state.latestCalculation.trees_needed} <span class="unit">trees / year</span>`;
            
            // Identify highest category
            const breakdown = state.latestCalculation.breakdown;
            const primary = Object.keys(breakdown).reduce((a, b) => breakdown[a] > breakdown[b] ? a : b);
            const primaryCapital = primary.charAt(0).toUpperCase() + primary.slice(1);
            document.getElementById('dash-primary-source').textContent = primaryCapital;
        }

        // Fetch Goals
        const goalsRes = await fetch('/api/goals');
        state.goals = await goalsRes.json();
        renderGoals();

        // Fetch Badges
        const badgesRes = await fetch('/api/badges');
        state.badges = await badgesRes.json();
        renderBadges();

        // Check backend server settings
        updateServerConnectionBadges();

        // Load charts on Dashboard
        renderCharts();
        updateOffsetLedger();
        
    } catch (err) {
        console.error("Error fetching state updates: ", err);
    }
}

// Save calculations to database
async function saveCalculation() {
    try {
        const response = await fetch('/api/calculate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(state.calculatorInputs)
        });
        
        if (!response.ok) throw new Error("Calculation API error");
        
        const result = await response.json();
        
        // Refresh values
        await refreshData();
        
        // Switch to Dashboard Tab
        document.querySelector('.nav-item[data-tab="dashboard"]').click();
        
    } catch (err) {
        alert("Could not save calculation. Checking backend logs.");
        console.error(err);
    }
}

// Render goals list
function renderGoals() {
    const container = document.getElementById('goals-list-container');
    container.innerHTML = '';
    
    if (state.goals.length === 0) {
        container.innerHTML = '<div class="info-text">No active goals set up.</div>';
        return;
    }

    state.goals.forEach(goal => {
        const item = document.createElement('div');
        item.className = `goal-item ${goal.completed ? 'completed' : ''}`;
        item.innerHTML = `
            <div class="goal-checkbox" onclick="toggleGoal('${goal.id}', ${!goal.completed})"></div>
            <div class="goal-text">${goal.title}</div>
            <span class="goal-tag">${goal.category}</span>
        `;
        container.appendChild(item);
    });
}

// Toggle goals completion status
async function toggleGoal(goalId, completedState) {
    try {
        const res = await fetch(`/api/goals/${goalId}/toggle`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ completed: completedState })
        });
        
        if (!res.ok) throw new Error("Toggle Goal API failure");
        
        state.goals = await res.json();
        renderGoals();
        
        // Refresh badges/achievements
        const badgesRes = await fetch('/api/badges');
        state.badges = await badgesRes.json();
        renderBadges();
        
    } catch (err) {
        console.error("Error toggling goal:", err);
    }
}

// Render badges achievements
function renderBadges() {
    const container = document.getElementById('badges-container');
    container.innerHTML = '';
    
    if (state.badges.length === 0) {
        container.innerHTML = '<div class="info-text">No badges configured.</div>';
        return;
    }

    state.badges.forEach(badge => {
        const card = document.createElement('div');
        card.className = `badge-card ${badge.unlocked ? 'unlocked' : ''}`;
        card.innerHTML = `
            <div class="badge-icon">${badge.icon}</div>
            <div class="badge-title">${badge.title}</div>
            <div class="badge-desc">${badge.description}</div>
        `;
        container.appendChild(card);
    });
}

// Check and render connection statuses
function updateServerConnectionBadges() {
    // If running in local DB mode vs Firebase
    const isMockDB = state.history.length === 0 || state.history.every(item => item.id && item.id.startsWith("calc_"));
    const fbBadge = document.getElementById('status-firebase-badge');
    const fbDesc = document.getElementById('status-firebase-desc');
    const dbIndicatorText = document.getElementById('backend-status');
    const dbIndicator = document.querySelector('.status-indicator');

    if (isMockDB) {
        fbBadge.className = "badge badge-error";
        fbBadge.textContent = "Offline/Mock";
        fbDesc.innerHTML = "Running in <strong>Local Fallback Mode</strong>. Storing data to <code>local_db.json</code>. Setup <code>FIREBASE_CREDENTIALS_PATH</code> in .env to bind to Firestore.";
        dbIndicatorText.textContent = "Local Mock Database";
        dbIndicator.className = "status-indicator warning";
    } else {
        fbBadge.className = "badge badge-success";
        fbBadge.textContent = "Active";
        fbDesc.innerHTML = "Successfully writing and fetching footprints using <strong>Google Firebase Firestore</strong> in real time.";
        dbIndicatorText.textContent = "Firebase Connected";
        dbIndicator.className = "status-indicator online";
    }
    
    // We fetch details from `/api/metrics` to decide if Gemini is active
}

// Setup AI Coach chat inputs
function setupChatListeners() {
    const chatInput = document.getElementById('chat-input');
    const sendBtn = document.getElementById('btn-send-chat');

    const handleSend = async () => {
        const text = chatInput.value.trim();
        if (!text) return;

        // Add user bubble
        appendChatBubble(text, 'user');
        chatInput.value = '';

        // Add typing indicator bubble
        const loadingBubble = appendChatBubble("Thinking...", 'coach loading');
        
        try {
            // Hit Gemini Coach Endpoint
            const res = await fetch('/api/coach', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: text,
                    last_calculation: state.latestCalculation
                })
            });

            if (!res.ok) throw new Error("Coach API Error");
            const data = await res.json();
            
            // Remove typing bubble and add AI response
            loadingBubble.remove();
            appendChatBubble(data.response, 'coach');

        } catch (err) {
            loadingBubble.remove();
            appendChatBubble("Sorry, I had trouble parsing that query. Check FastAPI backend console reports.", 'coach');
            console.error(err);
        }
    };

    sendBtn.addEventListener('click', handleSend);
    chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') handleSend();
    });
}

function appendChatBubble(text, sender) {
    const chatWindow = document.getElementById('chat-messages');
    const bubble = document.createElement('div');
    bubble.className = `chat-message ${sender}`;
    bubble.innerHTML = `
        <div class="message-content">${text}</div>
    `;
    chatWindow.appendChild(bubble);
    chatWindow.scrollTop = chatWindow.scrollHeight;
    return bubble;
}

// Fetch CodeCarbon logs from backend
async function fetchDevMetrics() {
    try {
        const res = await fetch('/api/metrics');
        const metrics = await res.json();
        
        // Update header and developer dashboard elements
        document.getElementById('header-dev-emissions').textContent = `${metrics.emissions_g_co2.toFixed(4)}g`;
        
        // Update developer tab values if active
        if (state.activeTab === 'developer') {
            document.getElementById('dev-emissions').textContent = `${metrics.emissions_g_co2.toFixed(6)}g`;
            document.getElementById('dev-energy').textContent = `${metrics.energy_consumed_kwh.toFixed(6)} kWh`;
            document.getElementById('dev-uptime').textContent = `${metrics.uptime_seconds}s`;
            document.getElementById('dev-trees-sec').textContent = `${metrics.trees_offset_seconds.toFixed(4)}s`;
        }

        // Also check if Gemini config status needs updates in UI
        const gemRes = await fetch('/api/goals'); // checking connectivity
        const geminiBadge = document.getElementById('status-gemini-badge');
        const geminiDesc = document.getElementById('status-gemini-desc');
        
        // In this workspace, if Gemini key is loaded
        const hasGeminiKey = document.querySelector('.status-indicator').classList.contains('online'); // placeholder condition matching env
        // Let's inspect config state reported from API or backend status
        // Since we are mocking connection, let's keep it based on .env checks
        
    } catch (err) {
        console.error("Error loading developer metrics: ", err);
    }
}

document.getElementById('btn-refresh-metrics').addEventListener('click', fetchDevMetrics);


// Render Chart.js dashboards
function renderCharts() {
    if (state.history.length === 0) return;

    // --- Donut Chart ---
    const latest = state.latestCalculation || state.history[0];
    const breakdown = latest.breakdown;
    const donutCtx = document.getElementById('donutChart');
    if (donutCtx) {
        if (donutChart) donutChart.destroy();
        donutChart = new Chart(donutCtx, {
            type: 'doughnut',
            data: {
                labels: ['Transport', 'Energy', 'Diet', 'Waste'],
                datasets: [{
                    data: [breakdown.transport, breakdown.energy, breakdown.diet, breakdown.waste],
                    backgroundColor: [
                        '#06b6d4', // cyan (transport)
                        '#f59e0b', // amber (energy)
                        '#10b981', // emerald (diet)
                        '#ef4444'  // red (waste)
                    ],
                    borderWidth: 1,
                    borderColor: '#1f2937'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            color: '#9ca3af',
                            font: { family: 'Inter', size: 11 }
                        }
                    }
                }
            }
        });
    }

    // --- Historical Line Chart ---
    const lineCtx = document.getElementById('historyChart');
    if (lineCtx) {
        if (historyChart) historyChart.destroy();
        
        // Take up to 7 items, sorted chronological
        const subHistory = [...state.history].slice(0, 7).reverse();
        const labels = subHistory.map(item => {
            const date = new Date(item.timestamp);
            return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
        });
        const dataset = subHistory.map(item => item.total);

        historyChart = new Chart(lineCtx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Total Footprint (kg CO₂)',
                    data: dataset,
                    borderColor: '#10b981',
                    backgroundColor: 'rgba(16, 185, 129, 0.05)',
                    fill: true,
                    tension: 0.3,
                    borderWidth: 3,
                    pointBackgroundColor: '#10b981',
                    pointHoverRadius: 6
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        grid: { color: 'rgba(255, 255, 255, 0.05)' },
                        ticks: { color: '#9ca3af', font: { family: 'Inter', size: 10 } }
                    },
                    y: {
                        grid: { color: 'rgba(255, 255, 255, 0.05)' },
                        ticks: { color: '#9ca3af', font: { family: 'Inter', size: 10 } }
                    }
                },
                plugins: {
                    legend: {
                        display: false
                    }
                }
            }
        });
    }
}
