import ipaddress
import os
import re
from pathlib import Path

import yaml

from .models import Server


class InventoryError(ValueError):
    pass


class UniqueSafeLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        seen = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str):
                raise InventoryError(f'Line {key_node.start_mark.line + 1}: field names must be strings')
            if key in seen:
                raise InventoryError(f'Line {key_node.start_mark.line + 1}: duplicate field {key}')
            seen.add(key)
        return super().construct_mapping(node, deep)


def mapping(value, allowed, context):
    if not isinstance(value, dict) or set(value) - allowed:
        raise InventoryError(f'{context}: expected a mapping with only these fields: {sorted(allowed)}')
    return value


def string(value, context):
    if not isinstance(value, str) or not value or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise InventoryError(f'{context}: expected a nonempty string without control characters')
    return value


def load_inventory(path: Path) -> list[Server]:
    path = path.expanduser().absolute()
    try:
        raw = yaml.load(path.read_text(encoding='utf-8'), Loader=UniqueSafeLoader)
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise InventoryError(f'{path}: {exc}') from exc
    raw = mapping(raw, {'defaults', 'servers'}, 'inventory')
    defaults = mapping(raw.get('defaults', {}), {'user', 'port'}, 'defaults')
    # Validate defaults even when every server overrides them.
    _validate_port(defaults.get('port', 22), 'defaults.port')
    _validate_user(defaults.get('user', 'root'), 'defaults.user')
    entries = raw.get('servers')
    if not isinstance(entries, list) or not entries:
        raise InventoryError('servers: expected a nonempty list')
    servers, names = [], set()
    for index, entry in enumerate(entries, 1):
        context = f'servers[{index}]'
        entry = mapping(entry, {'name', 'host', 'port', 'user', 'identity_file'}, context)
        name = string(entry.get('name'), f'{context}.name')
        if name in names:
            raise InventoryError(f'{name}.name: duplicate server name')
        names.add(name)
        host = string(entry.get('host'), f'{name}.host')
        try:
            ipaddress.ip_address(host)
        except ValueError:
            if len(host) > 253 or not all(re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', label) for label in host.rstrip('.').split('.')):
                raise InventoryError(f'{name}.host: invalid address or domain name') from None
        port = _validate_port(entry.get('port', defaults.get('port', 22)), f'{name}.port')
        user = _validate_user(entry.get('user', defaults.get('user', 'root')), f'{name}.user')
        identity = None
        if 'identity_file' in entry:
            value = string(entry['identity_file'], f'{name}.identity_file')
            identity = Path(value).expanduser()
            if not identity.is_absolute():
                identity = path.parent / identity
            identity = identity.absolute()
            if not identity.is_file() or not os.access(identity, os.R_OK):
                raise InventoryError(f'{name}.identity_file: file does not exist or is not readable: {identity}')
        servers.append(Server(name, host, port, user, identity))
    return servers


def _validate_port(value, context):
    if type(value) is not int or not 1 <= value <= 65535:
        raise InventoryError(f'{context}: port must be an integer from 1 to 65535')
    return value


def _validate_user(value, context):
    value = string(value, context)
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.-]*[$]?', value):
        raise InventoryError(f'{context}: invalid username')
    return value
