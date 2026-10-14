/**
 * OSIsoft PI Vision Custom Symbol: GT-2420A Predictive Advisory Card
 * 
 * Integrates Module 3 CorrelationDigitalTwin FastAPI service with PI Vision.
 * Polls the FastAPI advisory endpoint and dynamically renders the executive
 * early warning card with root-cause attribution and operator actions.
 */

(function (PV) {
    "use strict";

    function symbolVis() { }
    PV.deriveVisualizationFromBase(symbolVis);

    var definition = {
        typeName: "gt2420a-advisory",
        displayName: "GT-2420A Predictive Advisory",
        datasourceBehavior: PV.Extensibility.Enums.DatasourceBehaviors.Single,
        iconUrl: "/PIVision/Scripts/app/editor/symbols/ext/Icons/sym-gt2420a-advisory.png",
        getDefaultConfig: function () {
            return {
                DataShape: "Value",
                Height: 560,
                Width: 700,
                ApiUrl: "http://localhost:8000/api/v1/advisory/latest",
                RefreshIntervalSeconds: 30,
                LookbackPoints: 24,
                ShowWitnessPeers: true,
                ShowActions: true,
                SimulateFault: "none"
            };
        },
        configOptions: function () {
            return [
                {
                    title: "Advisory Settings",
                    mode: "format"
                }
            ];
        }
    };

    symbolVis.prototype.init = function (scope, elem, $http, $interval) {
        this.onDataUpdate = dataUpdate;
        this.onConfigChange = configChange;

        scope.advisory = null;
        scope.loading = true;
        scope.error = null;

        var pollingTimer = null;

        function fetchAdvisory() {
            var url = scope.config.ApiUrl || "http://localhost:8000/api/v1/advisory/latest";
            var params = {
                lookback: scope.config.LookbackPoints || 24
            };

            if (scope.config.SimulateFault && scope.config.SimulateFault !== "none") {
                params.simulate_fault = scope.config.SimulateFault;
            }

            scope.loading = !scope.advisory;

            $http.get(url, { params: params, timeout: 8000 })
                .then(function (response) {
                    scope.advisory = response.data;
                    scope.loading = false;
                    scope.error = null;
                    updateSeverityStyles();
                })
                .catch(function (err) {
                    scope.loading = false;
                    scope.error = "Failed to connect to Predictive API: " + (err.statusText || err.message || "Network Error");
                });
        }

        function updateSeverityStyles() {
            if (!scope.advisory) return;

            var severity = scope.advisory.severity || "NORMAL";
            if (severity === "CRITICAL") {
                scope.badgeColor = "#ef4444"; // Red
                scope.badgeText = "CRITICAL (ANOMALY)";
            } else if (severity === "HIGH") {
                scope.badgeColor = "#f59e0b"; // Amber
                scope.badgeText = "WARNING";
            } else {
                scope.badgeColor = "#10b981"; // Green
                scope.badgeText = "NORMAL (HEALTHY)";
            }
        }

        function startPolling() {
            stopPolling();
            fetchAdvisory();
            var intervalMs = Math.max(10, (scope.config.RefreshIntervalSeconds || 30)) * 1000;
            pollingTimer = $interval(fetchAdvisory, intervalMs);
        }

        function stopPolling() {
            if (pollingTimer) {
                $interval.cancel(pollingTimer);
                pollingTimer = null;
            }
        }

        function dataUpdate(data) {
            // Optional: called if PI Vision supplies context attribute data
        }

        function configChange(newConfig, oldConfig) {
            if (newConfig.ApiUrl !== oldConfig.ApiUrl ||
                newConfig.RefreshIntervalSeconds !== oldConfig.RefreshIntervalSeconds ||
                newConfig.SimulateFault !== oldConfig.SimulateFault) {
                startPolling();
            }
        }

        scope.$on("$destroy", function () {
            stopPolling();
        });

        // Start initial data retrieval
        startPolling();
    };

    PV.symbolCatalog.register(definition);
})(window.PIVisualization);
