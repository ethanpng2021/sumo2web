from flask import Flask, render_template
from flask_socketio import SocketIO, emit
import traci
import time
import threading

app = Flask(__name__)
app.config['SECRET_KEY'] = 'A34F6g7JK0c5N'
socketio = SocketIO(app, async_mode='threading')

# Configurations
SUMO_BINARY = "sumo"  # or "sumo-gui" for the GUI version
SUMO_CFG_FILE = "osm.sumocfg"  # Update with your sumocfg path

def sumo_simulation():
    traci.start([SUMO_BINARY, "-c", SUMO_CFG_FILE])

    while traci.simulation.getMinExpectedNumber() > 0:
        traci.simulationStep()
        vehicles = []

        for vehicle_id in traci.vehicle.getIDList():
            position = traci.vehicle.getPosition(vehicle_id)
            gps_position = traci.simulation.convertGeo(*position)
            angle = traci.vehicle.getAngle(vehicle_id)  # Vehicle orientation in degrees
            vehicles.append({'id': vehicle_id, 'x': gps_position[0], 'y': gps_position[1], 'angle': angle})

            # Animate each vehicle as they appear one by one
            socketio.emit('update', vehicles)
            #time.sleep(0.1)  # Emit every second. Adjust here to reduce the overall vehicle speed.

        # Animate all in one shot
        #socketio.emit('update', vehicles)
        #time.sleep(0.1)  # Emit every second. Adjust here to reduce the overall vehicle speed.

    traci.close()

@socketio.on('connect')
def handle_connect():
    if not sumo_thread.is_alive():
        sumo_thread.start()

@app.route('/')
def index():
    return render_template('index.html', mapbox_token="pk.wQz89mZO19Sf6XyxhO05ig")

if __name__ == "__main__":
    sumo_thread = threading.Thread(target=sumo_simulation)
    socketio.run(app, debug=True, host="0.0.0.0")
