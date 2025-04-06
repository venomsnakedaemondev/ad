#!/bin/bash

# Script para instalar paquetes AUR usando paru
# Parámetro: Nombre del paquete
PACKAGE=$1

# Verificar si ya está instalado
if paru -Q $PACKAGE &>/dev/null; then
    echo "$PACKAGE ya está instalado."
    exit 0
fi

# Instalar el paquete
paru -S --noconfirm $PACKAGE
