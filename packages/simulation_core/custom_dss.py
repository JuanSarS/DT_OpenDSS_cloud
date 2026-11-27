import re
from pathlib import Path, PurePosixPath

from packages.common.custom_model_paths import CustomModelError, model_file, relative_model_path


# Only properties for circuit elements and controls. External code, reporting
# options and implicit/abbreviated properties are never passed to DSS.
_SOURCE = "bus1 bus2 basekv pu angle frequency phases mvasc3 mvasc1 isc3 isc1 x1r1 x0r0 r1 x1 r0 x0"
_PROPERTIES = {
    "circuit": _SOURCE,
    "vsource": _SOURCE + " basefreq model daily yearly duty spectrum enabled like",
    "line": "bus1 bus2 linecode length phases r1 x1 r0 x0 c1 c0 rmatrix xmatrix cmatrix switch units geometry spacing wires cncables tscables normamps emergamps enabled like",
    "linecode": "nphases r1 x1 r0 x0 c1 c0 units rmatrix xmatrix cmatrix basefreq normamps emergamps kron neutral faultrate pctperm repair like",
    "load": "bus1 phases conn model kv kw kvar kva pf daily yearly duty vminpu vmaxpu status zipv class enabled like",
    "loadshape": "npts interval minterval sinterval mult pmult qmult hour csvfile dblfile useactual pmax qmax like",
    "transformer": "phases windings wdg bus conn kv kva tap %r %rs buses conns kvs kvas taps xhl xht xlt xscarray %loadloss %noloadloss %imag ppm_antifloat maxtap mintap numtaps bank xfmrcode enabled like",
    "xfmrcode": "phases windings wdg conn kv kva tap %r %rs conns kvs kvas taps xhl xht xlt xscarray %loadloss %noloadloss %imag maxtap mintap numtaps like",
    "regcontrol": "transformer winding tapwinding vreg band ptratio ctprim r x bus delay tapdelay inversetime reversible revvreg revband revr revx revthreshold revdelay maxtapchange enabled like",
    "capacitor": "bus1 bus2 phases kvar kv conn cmatrix cuf r xl harm numsteps states enabled like",
    "capcontrol": "element terminal capacitor type ptratio ctratio onsetting offsetting delay delayoff deadtime vmin vmax voltoverride vbus enabled like",
    "swtcontrol": "switchedobj switchedterm action lock delay normal state reset basefreq enabled like",
    "reactor": "bus1 bus2 phases kvar kv conn r x rmatrix xmatrix parallel r1 r2 r0 z1 z2 z0 enabled like",
    "wiredata": "rdc rac runits gmrac gmrunits radius radunits diam normamps emergamps like",
    "cndata": "k diastrand gmrstrand rstrand epsr inslayer diains diacable rdc rac runits gmrac gmrunits radius radunits diam normamps emergamps like",
    "tsdata": "diashield tapelayer tapelap epsr inslayer diains diacable rdc rac runits gmrac gmrunits radius radunits diam normamps emergamps like",
    "linegeometry": "nconds nphases cond wire cncable tscable x h units normamps emergamps reduce spacing wires cncables tscables like",
    "linespacing": "nconds nphases x h units like",
    "generator": "bus1 phases conn kv kw pf kvar kva model daily yearly duty vminpu vmaxpu enabled like",
    "pvsystem": "bus1 phases conn kv irradiance pmpp %pmpp temperature pf kvar kva cutin cutout effcurve ptcurve daily yearly duty varfollowinverter vminpu vmaxpu enabled like",
    "storage": "bus1 phases conn kv kw kvar pf kva kwrated kwhrated kwhstored %stored %reserve %charge %discharge state dispmode daily yearly duty vminpu vmaxpu enabled like",
    "xycurve": "npts xarray yarray points xshift yshift xscale yscale like",
}
_SET_OPTIONS = frozenset("defaultbasefrequency frequency voltagebases tolerance algorithm controlmode maxiterations maxcontroliter".split())
_FILE_PROPERTIES = {"csvfile": {".csv", ".txt"}, "dblfile": {".dbl"}}
_DATA_EXTENSIONS = {".csv", ".txt", ".dat", ".dbl"}
_TOKEN = re.compile(r"""[ \t]+|"[^"]*"|'[^']*'|[=()[\],~|]|[^ \t"'=()[\],~|!]+""")
_ATOM = re.compile(r"[a-zA-Z0-9_.%+-]+")
_QUOTED_ATOM = re.compile(r"[a-zA-Z0-9_.%+ -]+")
_OBJECT = re.compile(r"([a-zA-Z]+)\.([a-zA-Z0-9_./-]+)")
_LINECODE_NAME = re.compile(r"[a-zA-Z0-9_.-]+(?:/[a-zA-Z0-9_][a-zA-Z0-9_.-]*)*")
_MAX_INCLUDE_DEPTH = 24
_MAX_SCRIPT_BYTES = 25 * 1024 * 1024


def _tokens(line: str) -> list[str]:
    result = []
    position = 0
    while position < len(line) and not line.startswith(("!", "//"), position):
        match = _TOKEN.match(line, position)
        if match is None:
            raise CustomModelError("Comillas o caracteres inválidos.")
        token = match[0]
        if not token.isspace():
            result.append(token)
        position = match.end()
    return result


def _named_values(tokens: list[str]):
    position = 0
    while position < len(tokens):
        if position + 2 >= len(tokens) or tokens[position + 1] != "=":
            raise CustomModelError("Use propiedades completas con la forma nombre=valor.")
        name = tokens[position].lower()
        start = position + 2
        end = start + 1
        if tokens[start] in ("(", "["):
            closing = ")" if tokens[start] == "(" else "]"
            try:
                end = tokens.index(closing, end) + 1
            except ValueError as exc:
                raise CustomModelError("El valor de la propiedad no está cerrado.") from exc
        yield name, tokens[start:end]
        position = end + (end < len(tokens) and tokens[end] == ",")


def _value(values: list[str]) -> str:
    if len(values) == 1:
        token = values[0]
        if _ATOM.fullmatch(token):
            return token
        if token.startswith(("'", '"')) and _QUOTED_ATOM.fullmatch(token[1:-1]):
            return f'"{token[1:-1]}"'
    elif values[0] in ("(", "[") and all(
        token in {",", "|", "/", "*", "+", "-"} or _ATOM.fullmatch(token)
        for token in values[1:-1]
    ):
        return f"{values[0]}{' '.join(values[1:-1])}{values[-1]}"
    raise CustomModelError("Valor de propiedad no admitido.")


def _file_reference(workspace: Path, directory: PurePosixPath, values: list[str], extensions: set[str]) -> Path:
    if len(values) != 1:
        raise CustomModelError("Indique un solo archivo y use comillas si su ruta contiene espacios.")
    name = values[0]
    if name.startswith(("'", '"')):
        name = name[1:-1]
    return model_file(workspace, relative_model_path(name, base=directory), extensions)


def _quote_path(path: Path) -> str:
    name = path.as_posix()
    if any(character in name for character in ('"', '\r', '\n')):
        raise CustomModelError("La ruta del archivo contiene caracteres no admitidos por DSS.")
    return f'"{name}"'


def _properties(
    tokens: list[str],
    element: str,
    workspace: Path,
    directory: PurePosixPath,
) -> str:
    allowed = _SET_OPTIONS if element == "set" else _PROPERTIES[element].split()
    properties = []
    for name, values in _named_values(tokens):
        if element == "transformer" and name == "ppm":
            name = "ppm_antifloat"
        if name not in allowed:
            raise CustomModelError(f"Propiedad no admitida para {element}: {name}.")
        if element == "loadshape" and name in _FILE_PROPERTIES:
            value = _quote_path(_file_reference(workspace, directory, values, _FILE_PROPERTIES[name]))
        elif element == "loadshape" and name in {"mult", "pmult", "qmult", "hour"} and (
            len(values) > 3 and values[1].lower() == "file" and values[2] == "="
        ):
            options = list(_named_values(values[1:-1]))
            path = _file_reference(workspace, directory, options[0][1], _DATA_EXTENSIONS)
            parameters = [f"file={_quote_path(path)}"]
            for option, argument in options[1:]:
                if option not in {"col", "header"} or len(argument) != 1:
                    raise CustomModelError(f"Opción de perfil no admitida: {option}.")
                parameters.append(f"{option}={_value(argument)}")
            value = f"({', '.join(parameters)})"
        elif element == "line" and name == "linecode" and len(values) == 1 and _LINECODE_NAME.fullmatch(values[0]):
            value = values[0]
        elif element == "set" and name == "voltagebases" and len(values) == 1 and values[0].startswith(("'", '"')):
            numbers = values[0][1:-1]
            if not re.fullmatch(r"[0-9., eE+-]+", numbers):
                raise CustomModelError("Las bases de tensión deben ser números.")
            value = f"[{numbers}]"
        else:
            value = _value(values)
        properties.append(f"{name}={value}")
    return " ".join(properties)


def custom_model_commands(workspace: Path, master: Path) -> list[str]:
    """Expand local includes and send only checked circuit commands to AltDSS."""
    remaining = _MAX_SCRIPT_BYTES
    commands = []

    def read_script(script: Path, active: tuple[Path, ...]) -> None:
        nonlocal remaining
        relative = PurePosixPath(script.relative_to(workspace).as_posix())
        if script in active or len(active) >= _MAX_INCLUDE_DEPTH:
            raise CustomModelError(f"Dependencia DSS cíclica o demasiado profunda: {relative}.")
        with script.open("rb") as stream:
            data = stream.read(remaining + 1)
        remaining -= len(data)
        if remaining < 0:
            raise CustomModelError("Las dependencias DSS superan el tamaño máximo permitido.")
        try:
            lines = data.decode("utf-8-sig").splitlines()
        except UnicodeDecodeError as exc:
            raise CustomModelError(f"{relative} debe estar codificado en UTF-8.") from exc

        active_element = None
        for number, line in enumerate(lines, 1):
            try:
                tokens = _tokens(line)
                if not tokens:
                    continue
                command, *arguments = tokens
                identifier, separator, prop = command.rpartition(".")
                if separator and arguments[:1] == ["="]:
                    command, arguments = "edit", [identifier, prop, *arguments]
                command = command.lower()
                if command in {"new", "edit"} and arguments:
                    if arguments[0].lower() == "object" and arguments[1:2] == ["="]:
                        arguments = arguments[2:]
                    identifier = arguments[0] if arguments else ""
                    target = _OBJECT.fullmatch(identifier.strip("'\""))
                    if target is None or target[1].lower() not in _PROPERTIES:
                        raise CustomModelError("Use una clase eléctrica admitida y un nombre de objeto.")
                    active_element = target[1].lower()
                    if "/" in target[2] and (active_element != "linecode" or not _LINECODE_NAME.fullmatch(target[2])):
                        raise CustomModelError("El nombre del objeto contiene separadores no admitidos.")
                    props = _properties(arguments[1:], active_element, workspace, relative.parent)
                    commands.append(f"{command} {target[0]} {props}")
                    continue
                if command == "~" and active_element is not None and arguments:
                    commands.append(f"~ {_properties(arguments, active_element, workspace, relative.parent)}")
                    continue

                active_element = None
                if command in {"clear", "calcvoltagebases", "calcv", "makebuslist", "solve"} and not arguments:
                    commands.append(command)
                elif command == "set" and arguments:
                    commands.append(f"set {_properties(arguments, 'set', workspace, relative.parent)}")
                elif command in {"redirect", "compile"}:
                    dependency = _file_reference(workspace, relative.parent, arguments, {".dss"})
                    read_script(dependency, (*active, script))
                elif command == "buscoords":
                    path = _file_reference(workspace, relative.parent, arguments, {".csv", ".txt", ".dat"})
                    commands.append(f"buscoords {_quote_path(path)}")
                else:
                    raise CustomModelError(f"Comando DSS no admitido: {command}.")
            except (CustomModelError, FileNotFoundError) as exc:
                raise CustomModelError(f"{relative.as_posix()}:{number} · {exc}") from exc

    read_script(master, ())
    return commands
