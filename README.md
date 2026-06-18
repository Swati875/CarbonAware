# Carbon - Interactive Footprint Tracker & AI Advisor

## Description
Carbon is an interactive footprint tracker and AI sustainability assistant. Built using a Python/FastAPI backend, it estimates your weekly carbon emissions based on daily habits such as transportation, energy usage, diet, and waste generation. Powered by Google Gemini AI, it offers an intelligent AI coach ("CarbonCoach") that provides contextual, tailored recommendations to help you minimize your carbon footprint. The application utilizes Firebase Firestore (with a local JSON database fallback) for robust data storage, keeping track of calculation histories, sustainability goals, and achievements. To ensure eco-friendly execution, the backend also integrates CodeCarbon to monitor its own server footprint while it runs.

## Key Features
- **Carbon Footprint Calculator:** Estimates carbon emissions from Transport, Energy, Diet, and Waste.
- **AI Sustainability Advisor (CarbonCoach):** Integrated with Google Gemini to offer contextual recommendations and actionable insights for lowering your carbon impact.
- **Goal Tracking & Gamification:** Set sustainability goals and earn badges (e.g., Carbon Slasher, Pedal Power) as you achieve a more eco-friendly lifestyle.
- **Server Emission Tracking:** Integrates CodeCarbon to estimate and display the backend server's carbon footprint in real-time.
- **Resilient Fallbacks:** Fallbacks to a smart rule-based AI advisor and a local JSON database if external APIs are not configured.

## Architecture

```mermaid
graph TD;
    Client[Web Dashboard / Client] --> |HTTP REST| FastAPI[FastAPI Backend Server];
    
    FastAPI --> |Calculates Emissions| CarbonUtils[Carbon Utils];
    FastAPI --> |Carbon Tracking| CC[CodeCarbon Tracker];
    FastAPI --> |AI Coaching| AI[Google Gemini API];
    FastAPI --> |Data Storage| DB[Firebase Firestore];
    
    subgraph Fallbacks
        AI -.-> |Fallback| MockAI[Rule-Based Mock Advisor];
        DB -.-> |Fallback| LocalDB[local_db.json];
    end
```
