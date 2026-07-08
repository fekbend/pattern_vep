import numpy as np
from psychopy import visual, core, event, monitors
import ctypes

# ==========================================
# 1. TRIGGERING MODULE
# ==========================================
class LabJackTrigger:
    """
    Handles TTL triggers via LabJack U3. 
    Gracefully falls back to a mock trigger if no LabJack is connected.
    """
    TRIGGERS = {
        'trial_start': 1,
        'trial_end': 2,
        'stopped_by_user': 3,
        'stim_offset': 10,
        'stim_onset': 11
    }

    def __init__(self, enable=True):
        self.enable = enable
        self.device = None
        
        if self.enable:
            try:
                import u3
                self.device = u3.U3()
                self._setEIOPort(0) # Clear port initially
                print("LabJack U3 connected successfully.")
            except Exception as e:
                print(f"Warning: LabJack not found or failed to connect ({e}). Running in Mock Mode.")
                self.enable = False
    
    def _setEIOPort(self, state):
        """Custom method for communicating with LabJack."""
        import u3
        cmd = u3.PortStateWrite([0, state, 0])
        fb = u3.PortStateRead()
        # Send commands and get feedback
        feedback = self.device.getFeedback(cmd, fb)
        return feedback[-1]['EIO']

    def send(self, trigger_name: str):
        """Sends a defined trigger code to the LabJack."""
        if trigger_name not in self.TRIGGERS:
            print(f"Trigger <{trigger_name}> not defined.")
            return

        code = self.TRIGGERS[trigger_name]
        
        if self.enable and self.device:
            self._setEIOPort(code)
            
        # Optional: Print to console for debugging
        print(f"[TTL Sent] {trigger_name} (Code: {code})")


# ==========================================
# 2. VEP TASK MODULE
# ==========================================
class PatternReversalVEP:
    """
    Handles the PsychoPy window, checkerboard generation, and timing loop.
    """
    def __init__(self, trigger_system, spatial_freq=0.5, fullscreen=True):
        self.trigger = trigger_system
        
        # 1. Fetch exact pixel resolution from Windows
        user32 = ctypes.windll.user32
        user32.SetProcessDPIAware() 
        screen_width_px = user32.GetSystemMetrics(0)
        screen_height_px = user32.GetSystemMetrics(1)
        
        # 2. Define the PHYSICAL setup
        viewing_distance_cm = 50.0  # Distance from eyes to screen
        screen_width_cm = 23.0      # Physical width of the display area
        
        # 3. Create a dynamic monitor profile
        my_mon = monitors.Monitor(
            name='AutoMonitor',
            distance=viewing_distance_cm,
            width=screen_width_cm
        )
        my_mon.setSizePix((screen_width_px, screen_height_px))
        
        # 4. Setup the Window using the monitor and VISUAL DEGREES
        self.win = visual.Window(
            size=(screen_width_px, screen_height_px), 
            monitor=my_mon,
            fullscr=fullscreen, 
            units='deg',
            color=[0, 0, 0], 
            allowGUI=False
        )
        self.win.mouseVisible = False

        # 2. Setup the Checkerboard Grating
        # A 2x2 numpy array representing a simple black (-1) and white (1) grid
        texture = np.array([[1, -1], 
                            [-1, 1]])
        
        self.checkerboard = visual.GratingStim(
            win=self.win,
            tex=texture,
            size=(max(self.win.size) * 2, max(self.win.size) * 2), # Cover entire screen
            sf=spatial_freq, # Spatial Frequency (Cycles per pixel)
            interpolate=False # Keep edges perfectly sharp
        )
        
        # 3. Setup a fixation cross to keep the subject's eyes steady
        self.fixation = visual.ShapeStim(
            win=self.win, 
            vertices=((0, -0.5), (0, 0.5), (0,0), (-0.5, 0), (0.5, 0)),
            lineWidth=3, 
            closeShape=False, 
            lineColor='red'
        )

    def run(self, reversals=100, freq_hz=2.0, baseline_sec=2.0):
        """
        Runs the pattern reversal protocol.
        freq_hz: Reversals per second (e.g., 2.0 = reverse every 0.5 seconds)
        """
        period = 1.0 / freq_hz
        
        # Draw gray baseline screen
        self.win.color = [0, 0, 0] # PsychoPy RGB range is -1 to 1. [0,0,0] is gray.
        self.fixation.draw()
        self.win.flip()
        
        print("\nStarting trial...")
        self.trigger.send('trial_start')
        core.wait(baseline_sec)

        # Main stimulation loop
        clock = core.Clock()
        next_reversal_time = clock.getTime() + period

        for i in range(reversals):
            # Check for emergency exit (ESC)
            if event.getKeys(['escape']):
                print("Task stopped by user.")
                self.trigger.send('stopped_by_user')
                break

            # Reverse the pattern logic
            self.checkerboard.tex = -self.checkerboard.tex
            
            # Prepare the next frame (draw to back buffer)
            self.checkerboard.draw()
            self.fixation.draw()
            
            # Busy-wait loop for microsecond accuracy until it's time to flip
            while clock.getTime() < next_reversal_time:
                pass 
            
            # Flip screen (synchronized to monitor vertical retrace)
            self.win.flip()
            
            # Immediately send trigger upon screen flip
            if i % 2 == 0:
                self.trigger.send('stim_onset')
            else:
                self.trigger.send('stim_offset')
                
            # Set target time for the NEXT reversal
            next_reversal_time += period

        # Cleanup
        self.win.color = [0, 0, 0]
        self.win.flip()
        core.wait(baseline_sec)
        self.trigger.send('trial_end')
        
    def close(self):
        self.win.mouseVisible = True
        self.win.close()
        core.quit()

# ==========================================
# 3. MAIN EXECUTION
# ==========================================
if __name__ == '__main__':
    # Initialize trigger (Set enable=False to test without LabJack)
    ttl_trigger = LabJackTrigger(enable=True)
    
    # Initialize task (Set fullscreen=False for easier debugging)
    vep_task = PatternReversalVEP(
        trigger_system=ttl_trigger, 
        spatial_freq=0.5, 
        fullscreen=True
    )
    
    try:
        # Run 10 reversals at 2 Hz (1 reversal every 0.5s)
        vep_task.run(reversals=150, freq_hz=2.0, baseline_sec=2.0)
    except Exception as e:
        print(f"Error occurred: {e}")
    finally:
        vep_task.close()