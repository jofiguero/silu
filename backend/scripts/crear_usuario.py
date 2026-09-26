"""Crea una cuenta desde el servidor.

    docker compose run --rm backend python scripts/crear_usuario.py \\
        --email tu@correo.cl --rol admin

La contraseña se pide de forma oculta y NUNCA se pasa como argumento: ahí
quedaría en el historial del shell, en la salida de `ps` para cualquier
proceso de la máquina, y en los logs de docker.
"""

from __future__ import annotations

import argparse
import getpass
import sys

from app.db.session import SessionFactory
from app.services.auth import AuthService

MINIMO = 12


def pedir_password() -> str:
    """Pide la contraseña dos veces, sin mostrarla."""
    while True:
        primera = getpass.getpass("Contraseña: ")

        if len(primera) < MINIMO:
            print(f"  Muy corta: al menos {MINIMO} caracteres.", file=sys.stderr)
            continue

        segunda = getpass.getpass("Repítela: ")
        if primera != segunda:
            print("  No coinciden.", file=sys.stderr)
            continue

        return primera


def main() -> int:
    parser = argparse.ArgumentParser(description="Crea una cuenta de Silu")
    parser.add_argument("--email", required=True, help="Correo con el que se entra")
    parser.add_argument(
        "--rol",
        default="usuario",
        choices=("admin", "usuario"),
        help="admin puede administrar; usuario solo ve lo suyo",
    )
    args = parser.parse_args()

    if not sys.stdin.isatty():
        # Sin terminal, getpass leería de una tubería y la contraseña podría
        # venir de un archivo o del historial. Mejor no dejarlo pasar.
        print(
            "Esto necesita una terminal interactiva. Usa 'docker compose run' "
            "(no 'exec -T' ni una tubería).",
            file=sys.stderr,
        )
        return 2

    password = pedir_password()

    with SessionFactory() as session:
        auth = AuthService(session)
        try:
            usuario = auth.crear_usuario(args.email, password, rol=args.rol)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    print(f"Listo: {usuario.email} ({usuario.role})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
