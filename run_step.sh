set -euo pipefail
export PATH="/c/Users/longb/rabbit-fem/.zig_wrappers:/usr/bin:/c/Users/longb/rabbit-fem/.venv/Scripts:$PATH"
cd "/c/Users/longb/rabbit-fem"
make -j8 METHOD=opt LIBMESH_DIR=/c/Users/longb/rabbit-fem/moose/libmesh/installed WASP_DIR=/c/Users/longb/rabbit-fem/moose/framework/contrib/wasp/install lib_suffix=a && if [ -f .libs/rabbit-opt.exe ]; then cp .libs/rabbit-opt.exe rabbit-opt.exe; elif [ -f .libs/rabbit-opt ]; then cp .libs/rabbit-opt rabbit-opt.exe; elif [ -f rabbit-opt ] && [ ! -f rabbit-opt.exe ]; then cp rabbit-opt rabbit-opt.exe; fi
