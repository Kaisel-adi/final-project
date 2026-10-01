/**
 * GCIR Maps Decorator System
 * Modern, mobile-first Leaflet map utilities providing:
 *  1. Locality / Subscale Map (Dashboard widget with radius circle & full-screen expand)
 *  2. Interactive Overview Map (Full-bleed with clustering & mobile Action Sheet preview)
 *  3. Focused Pinpoint & Location Picker Map (Detail view & Create/Edit report)
 */

window.GCIRMaps = (function () {
    'use strict';

    // Status Colors Mapping
    const STATUS_COLORS = {
        'Reported': '#ef4444',     // Red
        'Verified': '#f59e0b',     // Amber
        'Complained': '#8b5cf6',   // Purple
        'Resolved': '#10b981',     // Emerald
        'urgent': '#dc2626',       // Crimson
        'default': '#0d9488'       // Teal
    };

    /**
     * Debounce utility to prevent rapid successive function calls during user interactions
     */
    function debounce(fn, delay) {
        let timer = null;
        return function (...args) {
            clearTimeout(timer);
            timer = setTimeout(() => fn.apply(this, args), delay);
        };
    }

    /**
     * Creates a crisp SVG map pin DivIcon for Leaflet
     */
    function createMapPin(status, iconGlyph, isUser) {
        const color = isUser ? '#0d9488' : (STATUS_COLORS[status] || STATUS_COLORS['default']);
        const glyph = iconGlyph || (isUser ? 'my_location' : 'location_on');

        const html = `
            <div class="relative flex items-center justify-center cursor-pointer transition-transform hover:scale-110 active:scale-95" style="width: 36px; height: 46px; filter: drop-shadow(0 3px 6px rgba(0,0,0,0.35));">
                <svg viewBox="0 0 36 46" width="36" height="46" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M18 0C8.05887 0 0 8.05887 0 18C0 29.5 18 46 18 46C18 46 36 29.5 36 18C36 8.05887 27.9411 0 18 0Z" fill="${color}"/>
                    <circle cx="18" cy="18" r="13" fill="#ffffff"/>
                </svg>
                <span class="material-symbols-outlined absolute text-[18px] text-[${color}]" style="top: 8px; color: ${color};">
                    ${glyph}
                </span>
            </div>
        `;

        return L.divIcon({
            className: 'gcir-custom-pin',
            html: html,
            iconSize: [36, 46],
            iconAnchor: [18, 46],
            popupAnchor: [0, -42]
        });
    }

    /**
     * Standard OpenStreetMap / Carto tile layer
     */
    function createTileLayer() {
        return L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19,
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
            keepBuffer: 3,
            updateWhenIdle: true,
            updateWhenZooming: false
        });
    }

    /**
     * =========================================================================
     * 1. LOCALITY / SUBSCALE MAP (Dashboard Widget)
     * =========================================================================
     * Shows locality snippet centered on user's GPS/home with a radius circle
     * and a full-screen expand button.
     */
    function initLocalityMap(containerId, options) {
        options = options || {};
        const center = options.center || [28.6139, 77.2090]; // [lat, lon]
        const radiusKm = options.radiusKm || 3.0;
        const container = document.getElementById(containerId);
        if (!container) return null;

        // Ensure container has relative positioning for floating controls
        container.classList.add('relative', 'overflow-hidden');

        const map = L.map(containerId, {
            center: center,
            zoom: 13,
            zoomControl: false,
            scrollWheelZoom: false, // Prevents mobile page scroll trapping
            dragging: !L.Browser.mobile || options.draggable === true,
            tap: true
        });

        createTileLayer().addTo(map);

        // Add custom sleek zoom control in bottom-right
        L.control.zoom({ position: 'bottomright' }).addTo(map);

        // Semi-transparent Radius Boundary Circle (Teal / Emerald)
        const radiusMeters = radiusKm * 1000;
        const circle = L.circle(center, {
            radius: radiusMeters,
            color: '#0d9488',
            fillColor: '#0d9488',
            fillOpacity: 0.12,
            weight: 2,
            dashArray: '4, 6'
        }).addTo(map);

        // User Center Pin
        L.marker(center, { icon: createMapPin('default', 'home_pin', true) })
            .bindTooltip('Your Neighborhood Center', { direction: 'top' })
            .addTo(map);

        // Render Issue Pins if provided
        if (Array.isArray(options.issues)) {
            options.issues.forEach(issue => {
                if (issue.location && Array.isArray(issue.location.coordinates) && issue.location.coordinates.length === 2) {
                    const lat = issue.location.coordinates[1];
                    const lon = issue.location.coordinates[0];
                    const marker = L.marker([lat, lon], {
                        icon: createMapPin(issue.status, 'warning', false)
                    }).addTo(map);

                    marker.on('click', () => {
                        if (typeof options.onPinClick === 'function') {
                            options.onPinClick(issue);
                        } else if (issue.id || issue._id) {
                            window.location.href = `/reports/${issue.id || issue._id}`;
                        }
                    });
                }
            });
        }

        // Add Floating "Expand to Full Screen" Button
        const expandBtn = document.createElement('button');
        expandBtn.type = 'button';
        expandBtn.className = 'absolute top-3 right-3 z-[400] bg-white/95 hover:bg-white text-slate-800 p-2 rounded-xl shadow-md border border-slate-200/80 flex items-center gap-1.5 text-xs font-semibold backdrop-blur-sm active:scale-95 transition-all';
        expandBtn.innerHTML = `
            <span class="material-symbols-outlined text-lg text-emerald-600">fullscreen</span>
            <span class="hidden sm:inline">Expand Map</span>
        `;
        expandBtn.addEventListener('click', () => {
            if (typeof options.onExpand === 'function') {
                options.onExpand();
            } else {
                window.location.href = `/feed?view=map&lat=${center[0]}&lon=${center[1]}&radius=${radiusKm}`;
            }
        });
        container.appendChild(expandBtn);

        // Mobile Tap-to-Enable Dragging (Prevents accidental scrolling)
        if (L.Browser.mobile && !options.draggable) {
            const dragHint = document.createElement('div');
            dragHint.className = 'absolute bottom-2 left-2 z-[400] bg-black/60 text-white text-[10px] px-2 py-1 rounded-md backdrop-blur-sm pointer-events-none transition-opacity';
            dragHint.textContent = 'Tap to explore map';
            container.appendChild(dragHint);

            map.on('click', () => {
                map.dragging.enable();
                dragHint.style.opacity = '0';
                setTimeout(() => dragHint.remove(), 300);
            });
        }

        return { map, circle };
    }

    /**
     * =========================================================================
     * 2. INTERACTIVE OVERVIEW MAP (Report Map Page)
     * =========================================================================
     * Full interactive map with geolocation, search, and mobile Action Sheet drawer.
     */
    function initOverviewMap(containerId, options) {
        options = options || {};
        const center = options.center || [28.6139, 77.2090];
        const radiusKm = options.radiusKm || 5.0;
        const container = document.getElementById(containerId);
        if (!container) return null;

        const map = L.map(containerId, {
            center: center,
            zoom: 13,
            zoomControl: false
        });

        createTileLayer().addTo(map);
        L.control.zoom({ position: 'bottomright' }).addTo(map);

        // Marker layer group
        const markerGroup = L.layerGroup().addTo(map);

        // Floating Action Sheet Container on Mobile (slide-up issue card)
        let actionSheet = document.getElementById('map-action-sheet');
        if (!actionSheet) {
            actionSheet = document.createElement('div');
            actionSheet.id = 'map-action-sheet';
            actionSheet.className = 'fixed bottom-16 inset-x-0 z-40 p-4 transform translate-y-full transition-transform duration-300 ease-out pointer-events-none lg:static lg:transform-none lg:p-0';
            document.body.appendChild(actionSheet);
        }

        function showIssueActionSheet(props) {
            actionSheet.innerHTML = `
                <div class="pointer-events-auto bg-white rounded-2xl p-4 shadow-2xl border border-slate-200/90 max-w-md mx-auto relative animate-fade-in">
                    <button type="button" class="absolute top-3 right-3 text-slate-400 hover:text-slate-600 p-1" onclick="document.getElementById('map-action-sheet').classList.add('translate-y-full')">
                        <span class="material-symbols-outlined text-lg">close</span>
                    </button>
                    <a href="/reports/${props.id}" class="block group">
                        <div class="flex items-center gap-2 mb-2">
                            <span class="status-pill status-pill-${(props.status || 'Reported').toLowerCase()}">
                                <span class="status-pill-dot"></span>
                                <span>${props.status || 'Reported'}</span>
                            </span>
                            <span class="text-xs text-slate-500 font-medium">• ${props.distance_km || 0} km away</span>
                        </div>
                        <h4 class="font-bold text-slate-900 group-hover:text-emerald-600 transition-colors text-sm line-clamp-1 mb-1">
                            ${props.category_label || props.category || 'Civic Issue'}
                        </h4>
                        <p class="text-xs text-slate-600 line-clamp-2 mb-3">
                            ${props.description || 'No description provided.'}
                        </p>
                        <div class="flex items-center justify-between pt-2 border-t border-slate-100">
                            <span class="text-xs font-semibold text-slate-500 flex items-center gap-1">
                                <span class="material-symbols-outlined text-sm text-rose-500">favorite</span>
                                ${props.upvote_count || 0} Verifications
                            </span>
                            <span class="text-xs font-bold text-emerald-600 group-hover:underline flex items-center gap-0.5">
                                View Details <span class="material-symbols-outlined text-sm">arrow_forward</span>
                            </span>
                        </div>
                    </a>
                </div>
            `;
            actionSheet.classList.remove('translate-y-full');
        }

        // Fetch reports via GeoJSON API
        function loadReports(lat, lon, radius, category, status) {
            markerGroup.clearLayers();
            const apiUrl = `/feed/api/reports?lat=${lat}&lon=${lon}&radius=${radius}&category=${category || ''}&status=${status || ''}&limit=100`;

            fetch(apiUrl)
                .then(r => r.json())
                .then(data => {
                    if (data && data.features) {
                        data.features.forEach(f => {
                            if (f.geometry && f.geometry.coordinates) {
                                const fLat = f.geometry.coordinates[1];
                                const fLon = f.geometry.coordinates[0];
                                const marker = L.marker([fLat, fLon], {
                                    icon: createMapPin(f.properties.status, 'warning', false)
                                }).addTo(markerGroup);

                                marker.on('click', () => {
                                    showIssueActionSheet(f.properties);
                                });
                            }
                        });
                    }
                })
                .catch(err => console.error('Map report fetch failed:', err));
        }

        loadReports(center[0], center[1], radiusKm, options.category, options.status);

        // Debounced Map Movement Handler: reload visible reports on pan/zoom without flooding the server
        const debouncedLoadVisibleReports = debounce(() => {
            const mapCenter = map.getCenter();
            const bounds = map.getBounds();
            const northEast = bounds.getNorthEast();
            const visibleRadiusKm = Math.min(Math.max(1.0, mapCenter.distanceTo(northEast) / 1000.0), 100.0);
            loadReports(mapCenter.lat, mapCenter.lng, visibleRadiusKm.toFixed(1), options.category, options.status);
        }, 350);

        map.on('moveend', debouncedLoadVisibleReports);

        // "Locate Me" Geolocation Control Button
        const locateBtn = document.createElement('button');
        locateBtn.type = 'button';
        locateBtn.className = 'absolute top-3 left-3 z-[400] bg-white/95 hover:bg-white text-slate-800 p-2 rounded-xl shadow-md border border-slate-200/80 flex items-center gap-1.5 text-xs font-semibold backdrop-blur-sm active:scale-95 transition-all';
        locateBtn.innerHTML = `
            <span class="material-symbols-outlined text-lg text-emerald-600">my_location</span>
            <span class="hidden sm:inline">My Location</span>
        `;
        locateBtn.addEventListener('click', () => {
            if ("geolocation" in navigator) {
                locateBtn.disabled = true;
                navigator.geolocation.getCurrentPosition(pos => {
                    const uLat = pos.coords.latitude;
                    const uLon = pos.coords.longitude;
                    map.setView([uLat, uLon], 14);
                    loadReports(uLat, uLon, radiusKm, options.category, options.status);
                    locateBtn.disabled = false;
                }, () => {
                    alert('Geolocation access unavailable or denied.');
                    locateBtn.disabled = false;
                });
            }
        });
        container.appendChild(locateBtn);

        return { map, loadReports };
    }

    /**
     * =========================================================================
     * 3. FOCUSED PINPOINT / LOCATION PICKER MAP (Create & Detail Views)
     * =========================================================================
     * Pin picker for issue creation or exact coordinate display with expand toggle.
     */
    function initPinpointMap(containerId, options) {
        options = options || {};
        const coords = options.coords || [28.6139, 77.2090];
        const isPicker = options.isPicker !== false; // Draggable picker mode
        const container = document.getElementById(containerId);
        if (!container) return null;

        container.classList.add('relative', 'overflow-hidden');

        const map = L.map(containerId, {
            center: coords,
            zoom: 15,
            zoomControl: false,
            scrollWheelZoom: isPicker
        });

        createTileLayer().addTo(map);
        L.control.zoom({ position: 'bottomright' }).addTo(map);

        const marker = L.marker(coords, {
            draggable: isPicker,
            icon: createMapPin(options.status || 'Reported', isPicker ? 'edit_location' : 'pin_drop', false)
        }).addTo(map);

        if (isPicker) {
            function updateFormCoords(lat, lon) {
                const latInput = document.getElementById(options.latInputId || 'latitude');
                const lonInput = document.getElementById(options.lonInputId || 'longitude');
                if (latInput) latInput.value = lat.toFixed(6);
                if (lonInput) lonInput.value = lon.toFixed(6);
                if (typeof options.onCoordsChange === 'function') {
                    options.onCoordsChange(lat, lon);
                }
            }

            const debouncedUpdateCoords = debounce(updateFormCoords, 120);

            marker.on('drag', function (e) {
                const pos = marker.getLatLng();
                debouncedUpdateCoords(pos.lat, pos.lng);
            });

            marker.on('dragend', function (e) {
                const pos = marker.getLatLng();
                updateFormCoords(pos.lat, pos.lng);
            });

            map.on('click', function (e) {
                marker.setLatLng(e.latlng);
                updateFormCoords(e.latlng.lat, e.latlng.lng);
            });

            // "Detect My GPS" button
            const geolocateBtn = document.getElementById(options.geolocateBtnId || 'btn-geolocate');
            if (geolocateBtn) {
                geolocateBtn.addEventListener('click', function () {
                    if ("geolocation" in navigator) {
                        navigator.geolocation.getCurrentPosition(function (pos) {
                            const lat = pos.coords.latitude;
                            const lon = pos.coords.longitude;
                            map.setView([lat, lon], 16);
                            marker.setLatLng([lat, lon]);
                            updateFormCoords(lat, lon);
                        }, function () {
                            alert("Geolocation access denied or unavailable. Please click on the map to place the pin.");
                        }, { enableHighAccuracy: true });
                    }
                });
            }
        }

        // Full Screen Expansion Toggle
        const expandBtn = document.createElement('button');
        expandBtn.type = 'button';
        expandBtn.className = 'absolute top-3 right-3 z-[400] bg-white/95 hover:bg-white text-slate-800 p-2 rounded-xl shadow-md border border-slate-200/80 flex items-center gap-1.5 text-xs font-semibold backdrop-blur-sm active:scale-95 transition-all';
        expandBtn.innerHTML = `
            <span class="material-symbols-outlined text-lg text-emerald-600">fullscreen</span>
            <span class="hidden sm:inline">Full Map</span>
        `;
        expandBtn.addEventListener('click', () => {
            window.location.href = `/feed?view=map&lat=${coords[0]}&lon=${coords[1]}`;
        });
        container.appendChild(expandBtn);

        return { map, marker };
    }

    // Public API
    return {
        initLocalityMap,
        initOverviewMap,
        initPinpointMap,
        createMapPin
    };
})();

// Modern Garuda Maps alias
window.GarudaMaps = window.GCIRMaps;
