// CITINOVA AI - Public Route Finder
// Talks to the Flask endpoints /api/geocode and /api/route.
// Route times are ESTIMATES (no live traffic provider is connected).

// Same-origin when served by Flask on port 5000, otherwise call Flask directly.
const API = location.port === "5000" ? "" : "http://127.0.0.1:5000";

const els = {
    form: document.getElementById("route-form"),
    source: document.getElementById("source"),
    destination: document.getElementById("destination"),
    findBtn: document.getElementById("find-btn"),
    message: document.getElementById("message"),
    results: document.getElementById("results"),
    routeList: document.getElementById("route-list"),
    steps: document.getElementById("steps"),
    locate: document.getElementById("locate"),
    swap: document.getElementById("swap"),
    suggestions: {
        source: document.getElementById("source-suggestions"),
        destination: document.getElementById("destination-suggestions")
    }
};

// Chosen points: { lat, lon, name } or null
const state = {
    points: { source: null, destination: null },
    routes: [],
    selected: 0
};

let map = null;
let routeLayers = [];
let markerLayers = [];

// ---------------------------------------------------------------- map

function initMap() {
    if (typeof L === "undefined") {
        showMessage(
            "The map library could not load. Check your internet connection and refresh.",
            "error"
        );
        return;
    }

    map = L.map("map").setView([20, 0], 2);

    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: "© OpenStreetMap contributors"
    }).addTo(map);
}

// ----------------------------------------------------------- messages

function showMessage(text, type = "info") {
    els.message.textContent = text;
    els.message.className = text ? `message ${type}` : "message";
}

function setBusy(busy) {
    els.findBtn.disabled = busy;
    els.findBtn.textContent = busy ? "Searching..." : "Find Route";
}

// -------------------------------------------------------- API helpers

async function callApi(path) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 30000);

    try {
        const response = await fetch(`${API}${path}`, { signal: controller.signal });
        let data = {};

        try {
            data = await response.json();
        } catch (ignored) {
            // response was not JSON; handled below
        }

        if (!response.ok) {
            throw new Error(data.error || `Request failed (${response.status})`);
        }

        return data;

    } catch (error) {
        if (error.name === "AbortError") {
            throw new Error("The request took too long. Please try again.");
        }

        if (error instanceof TypeError) {
            throw new Error(
                "Cannot reach the CITINOVA backend. Make sure Flask is running."
            );
        }

        throw error;
    } finally {
        clearTimeout(timer);
    }
}

async function geocode(text) {
    const data = await callApi(`/api/geocode?q=${encodeURIComponent(text)}`);
    return data.results;
}

// --------------------------------------------------------- place picking

function setPoint(which, place) {
    state.points[which] = place;
    els[which].value = place.name.length > 90 ? place.name.slice(0, 87) + "..." : place.name;
    hideSuggestions(which);
}

function hideSuggestions(which) {
    els.suggestions[which].hidden = true;
    els.suggestions[which].replaceChildren();
}

function showSuggestions(which, places) {
    const list = els.suggestions[which];
    list.replaceChildren();

    places.forEach(place => {
        const item = document.createElement("li");
        const button = document.createElement("button");

        button.type = "button";
        button.textContent = place.name;       // textContent: safe against HTML injection
        button.addEventListener("click", () => setPoint(which, place));

        item.appendChild(button);
        list.appendChild(item);
    });

    list.hidden = false;
}

async function searchPlaces(which) {
    const text = els[which].value.trim();

    if (text.length < 3) {
        showMessage("Type at least 3 characters to search.", "error");
        return;
    }

    showMessage("Searching places...");

    try {
        showSuggestions(which, await geocode(text));
        showMessage("Choose the correct place from the list.");
    } catch (error) {
        showMessage(error.message, "error");
    }
}

// If the user typed text but never picked a suggestion, use the top match.
async function resolvePoint(which, label) {
    if (state.points[which]) return;

    const text = els[which].value.trim();

    if (!text) {
        throw new Error(`Please enter a ${label}.`);
    }

    const places = await geocode(text);
    setPoint(which, places[0]);
}

// Editing the text invalidates a previously picked place.
["source", "destination"].forEach(which => {
    els[which].addEventListener("input", () => {
        state.points[which] = null;
        hideSuggestions(which);
    });
});

document.getElementById("search-source")
    .addEventListener("click", () => searchPlaces("source"));

document.getElementById("search-destination")
    .addEventListener("click", () => searchPlaces("destination"));

els.swap.addEventListener("click", () => {
    const a = state.points.source;
    state.points.source = state.points.destination;
    state.points.destination = a;

    const text = els.source.value;
    els.source.value = els.destination.value;
    els.destination.value = text;

    hideSuggestions("source");
    hideSuggestions("destination");
});

els.locate.addEventListener("click", () => {
    if (!navigator.geolocation) {
        showMessage("Your browser does not support location access.", "error");
        return;
    }

    showMessage("Getting your location...");

    navigator.geolocation.getCurrentPosition(
        position => {
            setPoint("source", {
                lat: position.coords.latitude,
                lon: position.coords.longitude,
                name: "My current location"
            });
            showMessage("Using your current location as the starting point.");
        },
        () => showMessage(
            "Could not get your location. Allow location access, or type a place instead. " +
            "(Phones only allow location on HTTPS or localhost.)",
            "error"
        ),
        { timeout: 10000 }
    );
});

// ------------------------------------------------------------ formatting

function formatDuration(seconds) {
    const minutes = Math.max(1, Math.round(seconds / 60));

    if (minutes < 60) return `${minutes} min`;

    const hours = Math.floor(minutes / 60);
    const rest = minutes % 60;

    return rest ? `${hours} h ${rest} min` : `${hours} h`;
}

function formatDistance(meters) {
    if (meters < 1000) return `${Math.round(meters)} m`;

    const km = meters / 1000;
    return `${km.toFixed(km < 10 ? 1 : 0)} km`;
}

// ------------------------------------------------------------- rendering

function clearMap() {
    routeLayers.forEach(layer => layer.remove());
    markerLayers.forEach(layer => layer.remove());
    routeLayers = [];
    markerLayers = [];
}

function drawRoutes() {
    if (!map) return;

    clearMap();

    // Draw alternatives first so the selected route sits on top
    const order = state.routes
        .map((_, index) => index)
        .sort((a, b) => (a === state.selected) - (b === state.selected));

    order.forEach(index => {
        const isSelected = index === state.selected;

        const line = L.polyline(state.routes[index].coordinates, {
            color: isSelected ? "#00b8ff" : "#7d8da6",
            weight: isSelected ? 7 : 5,
            opacity: isSelected ? 0.95 : 0.65,
            dashArray: isSelected ? null : "8 10"
        }).addTo(map);

        line.on("click", () => selectRoute(index));
        routeLayers.push(line);
    });

    [["source", "Start", "#20e3a2"], ["destination", "Destination", "#ff6464"]]
        .forEach(([which, label, color]) => {
            const point = state.points[which];

            if (!point) return;

            const marker = L.circleMarker([point.lat, point.lon], {
                radius: 9,
                color: "#ffffff",
                weight: 3,
                fillColor: color,
                fillOpacity: 1
            }).addTo(map);

            marker.bindTooltip(label, { direction: "top" });
            markerLayers.push(marker);
        });

    map.fitBounds(
        L.polyline(state.routes[state.selected].coordinates).getBounds(),
        { padding: [40, 40] }
    );
}

function renderRouteList() {
    els.routeList.replaceChildren();

    state.routes.forEach((route, index) => {
        const card = document.createElement("button");
        card.type = "button";
        card.className = "route-card" + (index === state.selected ? " selected" : "");

        const left = document.createElement("div");

        const label = document.createElement("div");
        label.className = "label";
        label.textContent = route.label;

        const time = document.createElement("div");
        time.className = "time";
        time.textContent = formatDuration(route.duration_s);

        left.append(label, time);

        const dist = document.createElement("div");
        dist.className = "dist";
        dist.textContent = formatDistance(route.distance_m);

        card.append(left, dist);
        card.addEventListener("click", () => selectRoute(index));

        els.routeList.appendChild(card);
    });
}

function renderSteps() {
    els.steps.replaceChildren();

    state.routes[state.selected].steps.forEach(step => {
        const item = document.createElement("li");

        const text = document.createElement("span");
        text.textContent = step.instruction;

        const meta = document.createElement("span");
        meta.className = "meta";
        meta.textContent = step.distance_m > 0 ? formatDistance(step.distance_m) : "";

        item.append(text, meta);
        els.steps.appendChild(item);
    });
}

function selectRoute(index) {
    state.selected = index;
    renderRouteList();
    renderSteps();
    drawRoutes();
}

// ------------------------------------------------------------ main flow

els.form.addEventListener("submit", async event => {
    event.preventDefault();

    setBusy(true);
    els.results.hidden = true;
    showMessage("Finding your route...");

    try {
        // One at a time: the search service allows 1 request per second
        await resolvePoint("source", "starting point");
        await resolvePoint("destination", "destination");

        const from = state.points.source;
        const to = state.points.destination;

        const data = await callApi(
            `/api/route?from_lat=${from.lat}&from_lon=${from.lon}` +
            `&to_lat=${to.lat}&to_lon=${to.lon}`
        );

        state.routes = data.routes;
        state.selected = 0;

        els.results.hidden = false;
        renderRouteList();
        renderSteps();
        drawRoutes();

        const extra = data.routes.length > 1
            ? `${data.routes.length} routes found. Tap one to compare.`
            : "1 route found (no alternative available for this trip).";

        showMessage(`${extra} Times are estimates, not live traffic.`);

        // On phones the map is below the form, so bring it into view
        if (window.innerWidth <= 900) {
            document.getElementById("map").scrollIntoView({ behavior: "smooth" });
        }

    } catch (error) {
        showMessage(error.message, "error");
    } finally {
        setBusy(false);
    }
});

initMap();
