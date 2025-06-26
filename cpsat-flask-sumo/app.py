from flask import Flask, render_template
from flask_socketio import SocketIO, emit
import traci
import time
import threading
#import eventlet
#eventlet.monkey_patch()
from ortools.sat.python import cp_model
from collections import defaultdict
from datetime import datetime, timedelta



app = Flask(__name__)
app.config['SECRET_KEY'] = 'A34F6g7J!!K0c5N'
socketio = SocketIO(app, async_mode='threading')



# Configurations
# "sumo-gui" for the GUI version
# "sumo" for the non-GUI version
SUMO_BINARY = "sumo"  
SUMO_CFG_FILE = "osm.sumocfg"  # Update with your sumocfg path

# Global variables for simulation control
simulation_thread = None
simulation_running = threading.Event()
simulation_running.clear()


def optimize_traffic_cp_sat(lane_vehicles):
    model = cp_model.CpModel()
    
    # Example: Each lane is associated with a phase
    phase_vars = {}
    for lane, count in lane_vehicles.items():
        # Assume each phase duration is between 10 and 60 seconds
        var = model.NewIntVar(10, 60, f'green_time_{lane}')
        phase_vars[lane] = var

    # Objective: maximize total vehicle throughput
    # e.g., total green time weighted by number of vehicles
    model.Maximize(sum(phase_vars[lane] * count for lane, count in lane_vehicles.items()))

    solver = cp_model.CpSolver()
    status = solver.Solve(model)

    result = {}
    if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        for lane, var in phase_vars.items():
            result[lane] = solver.Value(var)
    else:
        print("No solution found")
    
    return result


def apply_traffic_light_changes(optimized_phases):
    for lane, duration in optimized_phases.items():
        tls_id = traci.lane.getEdgeID(lane)  # Or use custom mapping
        current_phase_index = traci.trafficlight.getPhase(tls_id)
        try:
            traci.trafficlight.setPhaseDuration(tls_id, duration)
        except traci.TraCIException:
            print(f"Could not set duration for {tls_id}")


def sumo_simulation():
    global simulation_running
    try:
        traci.start([SUMO_BINARY, "-c", SUMO_CFG_FILE])
        
        while simulation_running.is_set() and traci.simulation.getMinExpectedNumber() > 0:
            
            traci.simulationStep()
            vehicles = []

            # -------------------------------
            vehicle_counts = defaultdict(int)
            last_reset_time = datetime.now()
            # -------------------------------

            for vehicle_id in traci.vehicle.getIDList():
                position = traci.vehicle.getPosition(vehicle_id)
                gps_position = traci.simulation.convertGeo(*position)
                angle = traci.vehicle.getAngle(vehicle_id)


                vehicles.append({
                    'id': vehicle_id, 
                    'x': gps_position[0], 
                    'y': gps_position[1], 
                    'angle': angle
                })


                # Comment out this block to capture 
                # original traffic flow scene without optimization
                # ------------------------------------------

                current_time = datetime.now()

                for vehicle in vehicles:
                    lane_id = traci.vehicle.getLaneID(vehicle['id'])
                    vehicle_counts[lane_id] += 1

                if (current_time - last_reset_time) >= timedelta(seconds=60):
                    # Use this data to optimize light phases
                    lane_vehicles_per_min = dict(vehicle_counts)

                    # Reset
                    vehicle_counts.clear()
                    last_reset_time = current_time

                    # Call optimization function
                    optimized_phases = optimize_traffic_cp_sat(lane_vehicles_per_min)
                    
                    # Apply the new phase durations
                    apply_traffic_light_changes(optimized_phases)

                # -------------------------------------------

            
            # Send vehicle updates to all clients
            socketio.emit('update', vehicles)
            time.sleep(0.05)  # Control update speed
            
        # Clean up when simulation stops
        traci.close()
        socketio.emit('simulation_status', {'status': 'stopped'})
        
    except Exception as e:
        print(f"Simulation error: {str(e)}")
        socketio.emit('simulation_error', {'message': str(e)})
    finally:
        simulation_running.clear()

@socketio.on('connect')
def handle_connect():
    emit('simulation_status', {'status': 'stopped' if not simulation_running.is_set() else 'running'})

@socketio.on('start_simulation')
def handle_start():
    global simulation_thread, simulation_running
    
    if not simulation_running.is_set():
        simulation_running.set()
        simulation_thread = threading.Thread(target=sumo_simulation)
        simulation_thread.daemon = True
        simulation_thread.start()
        emit('simulation_status', {'status': 'running'}, broadcast=True)

@socketio.on('stop_simulation')
def handle_stop():
    global simulation_running
    
    if simulation_running.is_set():
        simulation_running.clear()
        emit('simulation_status', {'status': 'stopping'}, broadcast=True)
        
        # Wait for simulation thread to finish
        if simulation_thread and simulation_thread.is_alive():
            simulation_thread.join(timeout=5.0)
        
        emit('simulation_status', {'status': 'stopped'}, broadcast=True)

@app.route('/')
def index():
    return render_template('index.html', mapbox_token="getyourownkeyatmapboxwebsite")

if __name__ == "__main__":
    socketio.run(app, debug=True, host="0.0.0.0", port=5000)


# June 2025. Penrose AGI, Singapore. 

