#!/usr/bin/env python3
import os
import sys
import json
import fcntl
import time
import shutil
import subprocess
import logging
from colorama import Fore, Style, init

init(autoreset=True)

# Configuración global
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "functions", "paquetes.json")
LOCK_FILE = "/tmp/arch_pkg_helper.lock"
PACMAN_LOCK = "/var/lib/pacman/db.lck"
PARU_URL = "https://aur.archlinux.org/paru-bin.git"
TEMP_DIR = "/tmp/paru_install"

# Configuración de logging
logging.basicConfig(
    filename='arch_pkg_helper.log',
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class PackageManager:
    def __init__(self):
        self.current_package = ""
        self.lock_file = None
        self.acquire_lock()

    def acquire_lock(self):
        try:
            self.lock_file = open(LOCK_FILE, "w")
            fcntl.flock(self.lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except IOError:
            self.log("Error: Ya hay otra instancia en ejecución", "error")
            sys.exit(1)

    def log(self, message, level="info"):
        # Cambié success por info para el color verde
        if level == "success":
            logging.info(message)
        else:
            getattr(logging, level)(message)
        
        colors = {
            'info': Fore.CYAN,
            'warning': Fore.YELLOW,
            'error': Fore.RED,
            'success': Fore.GREEN
        }
        print(colors.get(level, Fore.WHITE) + message)

    def load_config(self):
        try:
            with open(CONFIG_PATH) as f:
                config = json.load(f)
                if not all(k in config for k in ["pacman", "aur"]):
                    raise ValueError("Configuración inválida: deben existir las claves 'pacman' y 'aur'")
                if not isinstance(config["pacman"], list) or not isinstance(config["aur"], list):
                    raise ValueError("Configuración inválida: 'pacman' y 'aur' deben ser listas")
                return config
        except Exception as e:
            self.log(f"Error cargando configuración: {str(e)}", "error")
            sys.exit(1)

    def check_pacman_lock(self):
        if os.path.exists(PACMAN_LOCK):
            self.log("¡Pacman ya está en ejecución!", "warning")
            self.log("Espera a que termine o ejecuta: sudo rm /var/lib/pacman/db.lck", "info")
            return True
        return False

    def run_command(self, command, timeout=300, show_output=True):
        try:
            if self.check_pacman_lock():
                return 1, "Pacman bloqueado"

            self.log(f"Ejecutando: {' '.join(command)}")
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                universal_newlines=True
            )

            output = []
            while True:
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                if line and show_output:
                    print(Fore.BLUE + line.strip())
                    output.append(line)
                    sys.stdout.flush()

            returncode = process.poll()
            if returncode != 0:
                error = process.stderr.read()
                self.log(f"Error en {command[0]}: {error}", "error")
            return returncode, ''.join(output)

        except Exception as e:
            self.log(f"Excepción: {str(e)}", "error")
            return 1, ""

    def install_package(self, package, is_aur=False):
        for attempt in range(1, 4):
            self.log(f"Intento {attempt}/3 para {package}")
            if is_aur:
                cmd = ["paru", "-S", "--noconfirm", package]
            else:
                cmd = ["sudo", "pacman", "-S", "--noconfirm", package]
            code, _ = self.run_command(cmd, show_output=False)
            if code == 0:
                return True
            time.sleep(2)
        return False

    def install_paru(self):
        if self.run_command(["paru", "--version"])[0] == 0:
            return True

        self.log("Instalando paru desde AUR...", "info")
        try:
            os.makedirs(TEMP_DIR, exist_ok=True)
            os.chdir(TEMP_DIR)

            if not self._install_paru_dependencies():
                return False

            if not self._build_paru():
                return False

            if self.run_command(["paru", "--version"])[0] == 0:
                self.log("✓ Paru instalado correctamente", "success")
                return True
            else:
                self.log("✗ La instalación de paru falló", "error")
                return False

        except Exception as e:
            self.log(f"Error durante la instalación de paru: {str(e)}", "error")
            return False
        finally:
            shutil.rmtree(TEMP_DIR, ignore_errors=True)
            os.chdir(BASE_DIR)

    def _install_paru_dependencies(self):
        deps = ["git", "base-devel"]
        self.log("Instalando dependencias necesarias...", "info")

        for dep in deps:
            if self.run_command(["pacman", "-Qi", dep])[0] != 0:
                if self.run_command(["sudo", "pacman", "-S", "--noconfirm", "--needed", dep])[0] != 0:
                    self.log(f"✗ No se pudo instalar la dependencia: {dep}", "error")
                    return False
        return True

    def _build_paru(self):
        commands = [
            ["git", "clone", PARU_URL, "."],
            ["makepkg", "-si", "--noconfirm"],
            ["sudo", "pacman", "-U", "--noconfirm", "paru-bin*.pkg.tar.zst"]
        ]

        for cmd in commands:
            if self.run_command(cmd)[0] != 0:
                self.log(f"✗ Fallo en el comando: {' '.join(cmd)}", "error")
                return False
        return True

    def show_progress(self, current, total, pkg_name, stage, status=""):
        percent = (current/total)*100
        bar = '█' * int(percent/2) + '-' * (50 - int(percent/2))
        stage_color = Fore.BLUE if stage == "Pacman" else Fore.MAGENTA
        status_color = Fore.GREEN if "✓" in status else Fore.RED if "✗" in status else Fore.YELLOW

        sys.stdout.write(
            f"\r{stage_color}[{bar}] {percent:.1f}% "
            f"{Fore.YELLOW}{pkg_name[:25].ljust(25)} "
            f"{Fore.CYAN}{stage.ljust(6)} "
            f"{status_color}{status}"
        )
        sys.stdout.flush()

    def install_packages(self, pacman_pkgs, aur_pkgs=None):
        if not pacman_pkgs and not aur_pkgs:
            self.log("No hay paquetes para instalar", "warning")
            return False

        total = len(pacman_pkgs) + (len(aur_pkgs) if aur_pkgs else 0)
        success = 0
        count = 0

        if pacman_pkgs:
            self.log(f"\nInstalando {len(pacman_pkgs)} paquetes oficiales...", "info")
            for idx, pkg in enumerate(pacman_pkgs, 1):
                self.current_package = pkg
                count += 1
                self.show_progress(count, total, pkg, "Pacman", "Instalando...")

                if self.run_command(["pacman", "-Q", pkg])[0] == 0:
                    self.show_progress(count, total, pkg, "Pacman", "✓ Ya instalado")
                    success += 1
                elif self.install_package(pkg):
                    self.show_progress(count, total, pkg, "Pacman", "✓ Listo")
                    success += 1
                else:
                    self.show_progress(count, total, pkg, "Pacman", "✗ Error")

                time.sleep(0.5)

        if aur_pkgs:
            if not self.install_paru():
                return False

            self.log(f"\nInstalando {len(aur_pkgs)} paquetes AUR...", "info")
            for idx, pkg in enumerate(aur_pkgs, 1):
                self.current_package = pkg
                count += 1
                self.show_progress(count, total, pkg, "AUR", "Instalando...")

                if self.run_command(["paru", "-Q", pkg])[0] == 0:
                    self.show_progress(count, total, pkg, "AUR", "✓ Ya instalado")
                    success += 1
                elif self.install_package(pkg, is_aur=True):
                    self.show_progress(count, total, pkg, "AUR", "✓ Listo")
                    success += 1
                else:
                    self.show_progress(count, total, pkg, "AUR", "✗ Error")

                time.sleep(0.5)

        print("\n")
        if success == total:
            self.log("✓ Todos los paquetes instalados correctamente", "info")
        else:
            self.log(f"✓ {success}/{total} paquetes instalados", "warning")
        return success == total

    def show_menu(self):
        print(Fore.CYAN + "\n" + "="*50)
        print(f"{Fore.YELLOW}GESTOR DE PAQUETES ARCH LINUX".center(50))
        print(Fore.CYAN + "="*50)
        print(f"\n{Fore.GREEN}1. Instalar TODOS los paquetes")
        print(f"{Fore.BLUE}2. Mostrar paquetes configurados")
        print(f"{Fore.MAGENTA}3. Instalar solo paquetes oficiales (pacman)")
        print(f"{Fore.BLUE}4. Instalar solo paquetes AUR")
        print(f"{Fore.RED}5. Salir")
        return input(Fore.YELLOW + "\nSeleccione opción: ").strip()

    def list_packages(self, config):
        print(Fore.YELLOW + "\nPAQUETES OFICIALES (pacman):")
        for pkg in config["pacman"]:
            print(f"  - {pkg}")

        print(Fore.MAGENTA + "\nPAQUETES AUR:")
        for pkg in config["aur"]:
            print(f"  - {pkg}")

        print(Fore.CYAN + f"\nTotal: {len(config['pacman'])} paquetes oficiales")
        print(Fore.CYAN + f"       {len(config['aur'])} paquetes AUR")

    def run(self):
        config = self.load_config()

        while True:
            option = self.show_menu()

            if option == "1":
                self.install_packages(config["pacman"], config["aur"])
            elif option == "2":
                self.list_packages(config)
            elif option == "3":
                self.install_packages(config["pacman"])
            elif option == "4":
                self.install_packages([], config["aur"])
            elif option == "5":
                self.log("Saliendo...", "info")
                sys.exit(0)
            else:
                self.log("Opción inválida", "warning")

if __name__ == "__main__":
    PackageManager().run()
