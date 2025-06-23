import win32serviceutil
import win32service
import win32event
import servicemanager
import socket
import time
import sys
import os
import threading

# Attempt to import GUI libraries, but make them optional for core service functionality
try:
    from tkinter import Tk
    from PIL import Image, ImageTk
    HAS_TKINTER_PIL = True
except ImportError:
    HAS_TKINTER_PIL = False
    # servicemanager.LogWarningMsg("ShutdownInterceptorService: Tkinter or Pillow not found. Tray icon functionality will be limited or disabled.")


# Path to your icon file (replace with your actual icon path or ensure it's in the script's dir)
# Get the directory of the executable if frozen (e.g., with PyInstaller)
if getattr(sys, 'frozen', False):
    APPLICATION_PATH = os.path.dirname(sys.executable)
else:
    APPLICATION_PATH = os.path.dirname(os.path.abspath(__file__))
ICON_PATH = os.path.join(APPLICATION_PATH, "icon.ico")
LOG_FILE_PATH = os.path.join(APPLICATION_PATH, "shutdown_log.txt")


class ShutdownInterceptorService(win32serviceutil.ServiceFramework):
    _svc_name_ = "ShutdownInterceptorService"
    _svc_display_name_ = "Shutdown Interceptor Service"
    _svc_description_ = "Intercepts system shutdown/restart and provides a basic tray icon."

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        socket.setdefaulttimeout(60) # For any network ops the service might do
        self.is_running = True
        self.tray_thread = None
        self.tray_app_root = None
        servicemanager.LogInfoMsg(f"{self._svc_name_}: Service Initializing. Icon path: {ICON_PATH}, Log path: {LOG_FILE_PATH}")

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        servicemanager.LogInfoMsg(f"{self._svc_name_}: Service Stop Requested.")
        win32event.SetEvent(self.hWaitStop)
        self.is_running = False

        if self.tray_thread and self.tray_thread.is_alive():
            servicemanager.LogInfoMsg(f"{self._svc_name_}: Attempting to stop tray thread.")
            if self.tray_app_root and HAS_TKINTER_PIL:
                try:
                    self.tray_app_root.quit()
                    self.tray_app_root.destroy()
                    servicemanager.LogInfoMsg(f"{self._svc_name_}: Tkinter root quit and destroyed.")
                except Exception as e:
                    servicemanager.LogErrorMsg(f"{self._svc_name_}: Error quitting Tkinter: {str(e)}")
            self.tray_thread.join(timeout=5) # Wait for tray thread to finish
            if self.tray_thread.is_alive():
                servicemanager.LogWarningMsg(f"{self._svc_name_}: Tray thread did not stop gracefully.")

        servicemanager.LogInfoMsg(f"{self._svc_name_}: Service Stopped.")
        self.ReportServiceStatus(win32service.SERVICE_STOPPED)


    def SvcDoRun(self):
        servicemanager.LogMsg(servicemanager.EVENTLOG_INFORMATION_TYPE,
                              servicemanager.PYS_SERVICE_STARTED,
                              (self._svc_name_, ''))
        self.is_running = True # Ensure this is set at the start of SvcDoRun
        self.main()

    def main(self):
        servicemanager.LogInfoMsg(f"{self._svc_name_}: Service Main Loop Starting.")

        if HAS_TKINTER_PIL:
            self.tray_thread = threading.Thread(target=self.create_tray_icon_tkinter, daemon=True)
            self.tray_thread.start()
        else:
            servicemanager.LogWarningMsg(f"{self._svc_name_}: Tkinter/Pillow not available, tray icon will not be created.")

        # Main service loop
        while self.is_running:
            # Wait for the stop event, checking periodically
            result = win32event.WaitForSingleObject(self.hWaitStop, 1000) # Check every 1 second
            if result == win32event.WAIT_OBJECT_0:
                # Stop event was signaled
                self.is_running = False # Ensure loop terminates
                break

        servicemanager.LogInfoMsg(f"{self._svc_name_}: Service Main Loop Exited.")


    def create_tray_icon_tkinter(self):
        if not HAS_TKINTER_PIL:
            return

        try:
            servicemanager.LogInfoMsg(f"{self._svc_name_}: Tray icon thread started.")
            self.tray_app_root = Tk()
            self.tray_app_root.withdraw() # Hide the main Tkinter window

            # Try to load an icon
            if os.path.exists(ICON_PATH):
                try:
                    image = Image.open(ICON_PATH)
                    # For Tkinter's iconphoto, it usually wants a PhotoImage
                    # This sets the icon for the (hidden) window, which might appear in task manager
                    icon = ImageTk.PhotoImage(image)
                    self.tray_app_root.iconphoto(True, icon)
                    servicemanager.LogInfoMsg(f"{self._svc_name_}: Icon loaded for Tkinter window: {ICON_PATH}")
                except Exception as e:
                    servicemanager.LogErrorMsg(f"{self._svc_name_}: Error loading icon with PIL/Tkinter: {str(e)}")
            else:
                servicemanager.LogWarningMsg(f"{self._svc_name_}: Icon file not found: {ICON_PATH}")

            # This is a placeholder for where true tray icon logic (like pystray) would go.
            # Tkinter itself doesn't create a system tray (notification area) icon easily.
            # The main purpose of this Tkinter window in a service context (if not using pystray)
            # is to have a message loop that *might* be able to receive certain system messages
            # if the service is configured to interact with the desktop, though this is unreliable
            # for WM_QUERYENDSESSION for a typical service.

            # The mainloop will run until tray_app_root.quit() is called (e.g., in SvcStop)
            self.tray_app_root.mainloop()
            servicemanager.LogInfoMsg(f"{self._svc_name_}: Tkinter mainloop ended.")

        except Exception as e:
            servicemanager.LogErrorMsg(f"{self._svc_name_}: Error in Tkinter tray icon thread: {str(e)}")
        finally:
            if self.tray_app_root:
                try:
                    self.tray_app_root.destroy() # Ensure cleanup if mainloop exited unexpectedly
                except Exception as e:
                    servicemanager.LogErrorMsg(f"{self._svc_name_}: Error destroying Tkinter root in finally: {str(e)}")
            servicemanager.LogInfoMsg(f"{self._svc_name_}: Tray icon thread finished.")


    def SvcCtrlHandler(self, control):
        servicemanager.LogInfoMsg(f"{self._svc_name_}: Control Signal Received: {control}")
        if control == win32service.SERVICE_CONTROL_STOP:
            servicemanager.LogInfoMsg(f"{self._svc_name_}: SERVICE_CONTROL_STOP received.")
            self.SvcStop() # This will set self.is_running to False
        elif control == win32service.SERVICE_CONTROL_SHUTDOWN:
            servicemanager.LogInfoMsg(f"{self._svc_name_}: SERVICE_CONTROL_SHUTDOWN received.")
            self.shutdown_callback_placeholder("SERVICE_CONTROL_SHUTDOWN")
            # Service is expected to stop quickly after this.
            self.SvcStop() # Initiate service stop
        elif control == win32service.SERVICE_CONTROL_PRESHUTDOWN:
            servicemanager.LogInfoMsg(f"{self._svc_name_}: SERVICE_CONTROL_PRESHUTDOWN received.")
            # This is where you can perform longer tasks before shutdown is forced.
            # You cannot prevent shutdown from here.
            self.shutdown_callback_placeholder("SERVICE_CONTROL_PRESHUTDOWN")
            # The service doesn't necessarily stop itself here; SCM will proceed.
            # However, it's good practice to prepare for termination.
            # We don't call SvcStop() here as the system will terminate the service
            # after the preshutdown timeout if it hasn't stopped.
        else:
            # Pass other control codes to the base class handler
            self.ReportServiceStatus(self._svc_status_.dwCurrentState) # Acknowledge other signals


    def shutdown_callback_placeholder(self, event_source):
        """
        This is your placeholder for the shutdown callback.
        This function will be called when the service receives a shutdown signal
        from SCM (SERVICE_CONTROL_SHUTDOWN or SERVICE_CONTROL_PRESHUTDOWN).
        Add your custom logic here (e.g., save data, notify other systems).
        IMPORTANT: You CANNOT block or prevent the system shutdown from here.
        This is a notification to clean up and prepare for termination.
        """
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        log_message = f"{timestamp}: Shutdown event ({event_source}) intercepted by service '{self._svc_name_}'."
        servicemanager.LogInfoMsg(f"{self._svc_name_}: {log_message}")

        # --- BEGIN CUSTOM USER LOGIC ---
        # Example: Log to a specific file
        try:
            with open(LOG_FILE_PATH, "a") as f:
                f.write(log_message + "\n")
                f.write(f"{timestamp}: Placeholder: Performing custom shutdown tasks...\n")
            # Simulate some work (e.g., saving state, closing resources)
            time.sleep(5) # Simulate work for 5 seconds
            with open(LOG_FILE_PATH, "a") as f:
                f.write(f"{timestamp}: Placeholder: Custom shutdown tasks finished.\n")
            servicemanager.LogInfoMsg(f"{self._svc_name_}: Custom shutdown tasks simulated for {event_source}.")
        except Exception as e:
            err_msg = f"Error during shutdown_callback_placeholder: {str(e)}"
            servicemanager.LogErrorMsg(f"{self._svc_name_}: {err_msg}")
            try: # Try to log error to file as well
                with open(LOG_FILE_PATH, "a") as f:
                    f.write(f"{timestamp}: ERROR in shutdown_callback_placeholder: {str(e)}\n")
            except:
                pass # Ignore if logging to file also fails
        # --- END CUSTOM USER LOGIC ---

        return True # Standard practice, though return value isn't typically used by SCM here.


def install_service():
    try:
        servicemanager.LogInfoMsg(f"Attempting to install service '{ShutdownInterceptorService._svc_name_}'")
        # Use the class's module path and class name for InstallService
        module_path = os.path.abspath(sys.modules[ShutdownInterceptorService.__module__].__file__)
        win32serviceutil.InstallService(
            pythonClassString=f"{os.path.splitext(os.path.basename(module_path))[0]}.{ShutdownInterceptorService.__name__}",
            serviceName=ShutdownInterceptorService._svc_name_,
            displayName=ShutdownInterceptorService._svc_display_name_,
            description=ShutdownInterceptorService._svc_description_,
            startType=win32service.SERVICE_AUTO_START
        )
        servicemanager.LogInfoMsg(f"Service '{ShutdownInterceptorService._svc_name_}' installed successfully.")
        print(f"Service '{ShutdownInterceptorService._svc_name_}' installed successfully.")
        print(f"Module path used for install: {module_path}")
        print(f"Class string: {os.path.splitext(os.path.basename(module_path))[0]}.{ShutdownInterceptorService.__name__}")

        print(f"Attempting to start service '{ShutdownInterceptorService._svc_name_}'...")
        win32serviceutil.StartService(ShutdownInterceptorService._svc_name_)
        servicemanager.LogInfoMsg(f"Service '{ShutdownInterceptorService._svc_name_}' started successfully.")
        print(f"Service '{ShutdownInterceptorService._svc_name_}' started successfully.")

    except Exception as e:
        error_msg = f"Error during service installation or start: {str(e)}"
        servicemanager.LogErrorMsg(error_msg)
        print(f"ERROR: {error_msg}")
        if hasattr(e, 'msg'): print(f"Detailed error: {e.msg}")


def remove_service():
    try:
        servicemanager.LogInfoMsg(f"Attempting to stop service '{ShutdownInterceptorService._svc_name_}'")
        win32serviceutil.StopService(ShutdownInterceptorService._svc_name_)
        servicemanager.LogInfoMsg(f"Service '{ShutdownInterceptorService._svc_name_}' stopped successfully.")
        print(f"Service '{ShutdownInterceptorService._svc_name_}' stopped successfully.")
    except Exception as e:
        # Common error if service is not running: ERROR_SERVICE_NOT_ACTIVE
        if hasattr(e, 'winerror') and e.winerror == 1062: # ERROR_SERVICE_NOT_ACTIVE
             servicemanager.LogInfoMsg(f"Service '{ShutdownInterceptorService._svc_name_}' was not running.")
             print(f"Service '{ShutdownInterceptorService._svc_name_}' was not running.")
        else:
            error_msg = f"Error stopping service (it may already be stopped or not installed): {str(e)}"
            servicemanager.LogErrorMsg(error_msg)
            print(f"Warning: {error_msg}")

    try:
        servicemanager.LogInfoMsg(f"Attempting to remove service '{ShutdownInterceptorService._svc_name_}'")
        win32serviceutil.RemoveService(ShutdownInterceptorService._svc_name_)
        servicemanager.LogInfoMsg(f"Service '{ShutdownInterceptorService._svc_name_}' removed successfully.")
        print(f"Service '{ShutdownInterceptorService._svc_name_}' removed successfully.")
    except Exception as e:
        error_msg = f"Error removing service (it may not be installed): {str(e)}"
        servicemanager.LogErrorMsg(error_msg)
        print(f"ERROR: {error_msg}")


if __name__ == '__main__':
    # This part allows the script to be run from the command line
    # to install, start, stop, remove, or debug the service.
    # It also allows the Service Control Manager to run it as a service.

    if len(sys.argv) == 1:
        # Called by SCM, not by user command line
        try:
            servicemanager.Initialize()
            servicemanager.PrepareToHostSingle(ShutdownInterceptorService)
            servicemanager.StartServiceCtrlDispatcher()
        except win32service.error as details:
            import winerror
            if details.winerror == winerror.ERROR_FAILED_SERVICE_CONTROLLER_CONNECT:
                # This means it's likely being run directly (e.g., double-clicked)
                # and not by the SCM or with a command.
                print("This is a Windows service. Use command line options to manage it:")
                print(f"  python {os.path.basename(__file__)} install   (to install and start the service, requires Admin)")
                print(f"  python {os.path.basename(__file__)} start     (to start the service, requires Admin)")
                print(f"  python {os.path.basename(__file__)} stop      (to stop the service, requires Admin)")
                print(f"  python {os.path.basename(__file__)} remove    (to remove the service, requires Admin)")
                print(f"  python {os.path.basename(__file__)} debug     (to run the service in console for debugging)")
    else:
        # If called with command-line arguments, let win32serviceutil handle them.
        # Custom handlers for install/remove to provide more feedback.
        if sys.argv[1].lower() == 'install':
            print("Requesting to install and start service...")
            install_service()
        elif sys.argv[1].lower() == 'remove':
            print("Requesting to stop and remove service...")
            remove_service()
        else:
            # For 'start', 'stop', 'debug', 'update', etc.
            win32serviceutil.HandleCommandLine(ShutdownInterceptorService)

# --- Instructions for the user would typically go in a separate README or message ---
# This file itself is the Python script.
# User instructions will be provided in the next step of the plan.
# Key points for user:
# 1. Save this as shutdown_service.py
# 2. Install pywin32, Pillow: pip install pywin32 Pillow
# 3. Create icon.ico in the same directory or update ICON_PATH
# 4. Run as Admin:
#    python shutdown_service.py install
#    python shutdown_service.py remove
#    python shutdown_service.py debug
# 5. Add custom logic to shutdown_callback_placeholder function.
# 6. Check Windows Event Viewer (Application Log) and shutdown_log.txt for logs.
# 7. Service runs as LocalSystem; be mindful of permissions.
# 8. True shutdown *blocking* is complex and usually done by a GUI app, not directly by a service.
#    This service *intercepts* (gets notified of) shutdown.
# ------------------------------------------------------------------------------------
