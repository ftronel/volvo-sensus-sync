#!/bin/sh -x

IMPORT="/srv/musique/Musique/tagged"
EXTS="flac ogg opus"

cd ${IMPORT}
for EXT in ${EXTS}; do
	echo "Exporting files of format ${EXT}"
	find . -name "*.${EXT}" -type f -print
done
