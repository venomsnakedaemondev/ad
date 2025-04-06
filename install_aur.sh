#!/bin/bash

# Función para instalar paquetes desde AUR
install_aur_package() {
    local package=$1
    echo "Instalando $package desde AUR..."

    # Verificar si el paquete ya está instalado
    if pacman -Q $package &>/dev/null; then
        echo "$package ya está instalado."
    else
        # Instalación del paquete AUR
        yay -S --noconfirm $package
        if [ $? -eq 0 ]; then
            echo "✓ Instalación exitosa de $package."
        else
            echo "✗ Error al instalar $package."
        fi
    fi
}

# Validación del argumento
if [ -z "$1" ]; then
    echo "Error: No se especificó el nombre del paquete AUR."
    exit 1
fi

# Llamar a la función para instalar el paquete AUR
install_aur_package $1
