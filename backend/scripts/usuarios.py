"""Administra las cuentas desde el servidor.

    docker compose run --rm backend python scripts/usuarios.py listar
    docker compose run --rm backend python scripts/usuarios.py password --email x@y.cl
    docker compose run --rm backend python scripts/usuarios.py desactivar --email x@y.cl
    docker compose run --rm backend python scripts/usuarios.py activar --email x@y.cl
"""

from __future__ import annotations

import argparse
import sys

from app.db.session import SessionFactory
from app.services.auth import AuthService

from crear_usuario import pedir_password


def main() -> int:
    parser = argparse.ArgumentParser(description="Cuentas de Silu")
    sub = parser.add_subparsers(dest="accion", required=True)

    sub.add_parser("listar", help="Muestra todas las cuentas")

    for nombre, ayuda in [
        ("password", "Cambia la contraseña y cierra sus sesiones"),
        ("desactivar", "Le quita el acceso sin borrar sus datos"),
        ("activar", "Le devuelve el acceso"),
    ]:
        p = sub.add_parser(nombre, help=ayuda)
        p.add_argument("--email", required=True)

    args = parser.parse_args()

    with SessionFactory() as session:
        auth = AuthService(session)

        if args.accion == "listar":
            for u in auth.listar():
                estado = "activa" if u.is_active else "DESACTIVADA"
                visto = (
                    u.last_login_at.strftime("%Y-%m-%d %H:%M")
                    if u.last_login_at
                    else "nunca"
                )
                telegram = u.telegram_id or "sin vincular"
                print(
                    f"{u.email:<34} {u.role:<8} {estado:<12} "
                    f"último ingreso: {visto:<17} telegram: {telegram}"
                )
            return 0

        usuario = auth.buscar_por_email(args.email)
        if usuario is None:
            print(f"No existe ninguna cuenta con {args.email}", file=sys.stderr)
            return 1

        if args.accion == "password":
            if not sys.stdin.isatty():
                print("Esto necesita una terminal interactiva.", file=sys.stderr)
                return 2
            auth.cambiar_password(usuario, pedir_password())
            print(f"Contraseña cambiada. Se cerraron las sesiones de {usuario.email}.")
            return 0

        usuario.is_active = args.accion == "activar"
        if not usuario.is_active:
            # Desactivar tiene que echarlo ahora, no cuando venza su cookie.
            for sesion in usuario.sessions:
                session.delete(sesion)
        session.commit()
        print(f"{usuario.email}: {'activa' if usuario.is_active else 'desactivada'}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
