# SPDX-License-Identifier: GPL-2.0-or-later
#
# Copyright (C) 2026 Frédéric Tronel


PLANSH =  """#!/bin/sh
set -e

usage()
{
    cat <<EOF
Usage: $0 -d DIRECTORY

Options:
  -d, --directory DIR   Destination de la copie
  -h, --help            Affiche cette aide
EOF
}

DESTINATION=

while [ $# -gt 0 ]
do
    case "$1" in
        -h|--help)
            usage
            exit 0
            ;;

        -d|--directory)
            shift
            [ $# -gt 0 ] || {
                echo "Option $0: argument manquant." >&2
                exit 1
            }
            DESTINATION=$1
            ;;

        --)
            shift
            break
            ;;

        -*)
            echo "Option inconnue : $1" >&2
            usage >&2
            exit 1
            ;;

        *)
            echo "Argument inattendu : $1" >&2
            usage >&2
            exit 1
            ;;
    esac

    shift
done

[ -n "$DESTINATION" ] || {
    echo "L'option -d est obligatoire." >&2
    usage >&2
    exit 1
}

SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"

copy()
{
    echo "Copying $1 to $2"
    mkdir -p "$(dirname "$2")"
    cp -p "$1" "$2"
}



while IFS="$(printf '\t')" read -r RELSRC
do
    SRC="${SCRIPT_DIR}/${RELSRC}"
    DST="${DESTINATION}/${RELSRC}"
    copy "${SRC}" "${DST}"
done <<'__SYNC_PLAN__'
"""

