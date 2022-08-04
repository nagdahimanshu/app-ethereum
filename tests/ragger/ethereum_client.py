from contextlib import contextmanager
from enum import IntEnum, auto
from typing import Iterator, Dict, List
from ragger.backend import BackendInterface
from ragger.utils import RAPDU
import signal
import pdb

class   InsType(IntEnum):
    EIP712_SEND_STRUCT_DEF = 0x1a,
    EIP712_SEND_STRUCT_IMPL = 0x1c,
    EIP712_SEND_FILTERING = 0x1e,
    EIP712_SIGN = 0x0c

class   P1Type(IntEnum):
    COMPLETE_SEND = 0x00,
    PARTIAL_SEND = 0x01,
    FILTERING_ACTIVATE = 0x00,
    FILTERING_CONTRACT_NAME = 0x0f,
    FILTERING_FIELD_NAME = 0xff

class   P2Type(IntEnum):
    STRUCT_NAME = 0x00,
    STRUCT_FIELD = 0xff,
    ARRAY = 0x0f,
    LEGACY_IMPLEM = 0x00
    NEW_IMPLEM = 0x01

class   EIP712FieldType(IntEnum):
    CUSTOM = 0,
    INT = auto()
    UINT = auto()
    ADDRESS = auto()
    BOOL = auto()
    STRING = auto()
    FIX_BYTES = auto()
    DYN_BYTES = auto()

class   SettingType(IntEnum):
    BLIND_SIGNING = 0,
    DEBUG_DATA = auto()
    NONCE = auto()
    VERBOSE_EIP712 = auto()

class   Setting:
    devices: List[str]
    value: bool

    def __init__(self, d: List[str]):
        self.devices = d


class   EthereumClientCmdBuilder:
    _CLA: int = 0xE0

    def _serialize(self,
                   ins: InsType,
                   p1: int,
                   p2: int,
                   cdata: bytearray = bytearray()) -> bytes:

        header = bytearray()
        header.append(self._CLA)
        header.append(ins)
        header.append(p1)
        header.append(p2)
        header.append(len(cdata))
        return header + cdata

    def _string_to_bytes(self, string: str) -> bytes:
        data = bytearray()
        for char in string:
            data.append(ord(char))
        return data

    def eip712_send_struct_def_struct_name(self, name: str) -> bytes:
        return self._serialize(InsType.EIP712_SEND_STRUCT_DEF,
                               P1Type.COMPLETE_SEND,
                               P2Type.STRUCT_NAME,
                               self._string_to_bytes(name))

    def eip712_send_struct_def_struct_field(self,
                                            field_type: EIP712FieldType,
                                            type_name: str,
                                            type_size: int,
                                            array_levels: [],
                                            key_name: str) -> bytes:
        data = bytearray()
        typedesc = 0
        typedesc |= (len(array_levels) > 0) << 7
        typedesc |= (type_size != None) << 6
        typedesc |= field_type
        data.append(typedesc)
        if field_type == EIP712FieldType.CUSTOM:
            data.append(len(type_name))
            data += self._string_to_bytes(type_name)
        if type_size != None:
            data.append(type_size)
        if len(array_levels) > 0:
            data.append(len(array_levels))
            for level in array_levels:
                data.append(0 if level == None else 1)
                if level != None:
                    data.append(level)
        data.append(len(key_name))
        data += self._string_to_bytes(key_name)
        return self._serialize(InsType.EIP712_SEND_STRUCT_DEF,
                               P1Type.COMPLETE_SEND,
                               P2Type.STRUCT_FIELD,
                               data)

    def eip712_send_struct_impl_root_struct(self, name: str) -> bytes:
        return self._serialize(InsType.EIP712_SEND_STRUCT_IMPL,
                               P1Type.COMPLETE_SEND,
                               P2Type.STRUCT_NAME,
                               self._string_to_bytes(name))

    def eip712_send_struct_impl_array(self, size: int) -> bytes:
        data = bytearray()
        data.append(size)
        return self._serialize(InsType.EIP712_SEND_STRUCT_IMPL,
                               P1Type.COMPLETE_SEND,
                               P2Type.ARRAY,
                               data)

    def eip712_send_struct_impl_struct_field(self, data: bytearray) -> Iterator[bytes]:
        # Add a 16-bit integer with the data's byte length (network byte order)
        data_w_length = bytearray()
        data_w_length.append((len(data) & 0xff00) >> 8)
        data_w_length.append(len(data) & 0x00ff)
        data_w_length += data
        while len(data_w_length) > 0:
            p1 = P1Type.PARTIAL_SEND if len(data_w_length) > 0xff else P1Type.COMPLETE_SEND
            yield self._serialize(InsType.EIP712_SEND_STRUCT_IMPL,
                                  p1,
                                  P2Type.STRUCT_FIELD,
                                  data_w_length[:0xff])
            data_w_length = data_w_length[0xff:]

    def _format_bip32(self, bip32, data: bytearray) -> bytearray:
        data.append(len(bip32))
        for idx in bip32:
            data.append((idx & 0xff000000) >> 24)
            data.append((idx & 0x00ff0000) >> 16)
            data.append((idx & 0x0000ff00) >> 8)
            data.append((idx & 0x000000ff))
        return data

    def eip712_sign_new(self, bip32) -> bytes:
        data = self._format_bip32(bip32, bytearray())
        return self._serialize(InsType.EIP712_SIGN,
                               P1Type.COMPLETE_SEND,
                               P2Type.NEW_IMPLEM,
                               data)

    def eip712_sign_legacy(self,
                           bip32,
                           domain_hash: bytes,
                           message_hash: bytes) -> bytes:
        data = self._format_bip32(bip32, bytearray())
        data += domain_hash
        data += message_hash
        return self._serialize(InsType.EIP712_SIGN,
                               P1Type.COMPLETE_SEND,
                               P2Type.LEGACY_IMPLEM,
                               data)

    def eip712_filtering_activate(self):
        return self._serialize(InsType.EIP712_SEND_FILTERING,
                               P1Type.FILTERING_ACTIVATE,
                               0x00,
                               bytearray())

    def _eip712_filtering_send_name(self, name: str, sig: bytes) -> bytes:
        data = bytearray()
        data.append(len(name))
        data += self._string_to_bytes(name)
        data.append(len(sig))
        data += sig
        return data

    def eip712_filtering_send_contract_name(self, name: str, sig: bytes) -> bytes:
        return self._serialize(InsType.EIP712_SEND_FILTERING,
                               P1Type.FILTERING_CONTRACT_NAME,
                               0x00,
                               self._eip712_filtering_send_name(name, sig))

    def eip712_filtering_send_field_name(self, name: str, sig: bytes) -> bytes:
        return self._serialize(InsType.EIP712_SEND_FILTERING,
                               P1Type.FILTERING_FIELD_NAME,
                               0x00,
                               self._eip712_filtering_send_name(name, sig))


class   EthereumResponseParser:
    def sign(self, data: bytes):
        assert len(data) == (1 + 32 + 32)

        v = data[0:1]
        data = data[1:]

        r = data[0:32]
        data = data[32:]

        s = data[0:32]
        data = data[32:]

        return v, r, s

class   EthereumClient:
    _settings: Dict[SettingType, Setting] = {
        SettingType.BLIND_SIGNING: Setting(
            [ "nanos", "nanox", "nanosp" ]
        ),
        SettingType.DEBUG_DATA: Setting(
            [ "nanos", "nanox", "nanosp" ]
        ),
        SettingType.NONCE: Setting(
            [ "nanos", "nanox", "nanosp" ]
        ),
        SettingType.VERBOSE_EIP712: Setting(
            [ "nanox", "nanosp" ]
        )
    }
    _click_delay = 1/4
    _eip712_filtering = False

    def __init__(self, client: BackendInterface, debug: bool = False):
        self._client = client
        self._debug = debug
        self._cmd_builder = EthereumClientCmdBuilder()
        self._resp_parser = EthereumResponseParser()
        signal.signal(signal.SIGALRM, self._click_signal_timeout)
        for setting in self._settings.values():
            setting.value = False

    def _send(self, payload: bytearray):
        return self._client.exchange_async_raw(payload)

    def _recv(self) -> RAPDU:
        return self._client._last_async_response

    def _click_signal_timeout(self, signum: int, frame):
        self._client.right_click()

    def _enable_click_until_response(self):
        signal.setitimer(signal.ITIMER_REAL,
                         self._click_delay,
                         self._click_delay)

    def _disable_click_until_response(self):
        signal.setitimer(signal.ITIMER_REAL, 0, 0)

    def eip712_send_struct_def_struct_name(self, name: str):
        with self._send(self._cmd_builder.eip712_send_struct_def_struct_name(name)):
            pass
        return self._recv().status == 0x9000

    def eip712_send_struct_def_struct_field(self,
                                            field_type: EIP712FieldType,
                                            type_name: str,
                                            type_size: int,
                                            array_levels: [],
                                            key_name: str):
        with self._send(self._cmd_builder.eip712_send_struct_def_struct_field(
            field_type,
            type_name,
            type_size,
            array_levels,
            key_name)):
            pass
        return self._recv()

    def eip712_send_struct_impl_root_struct(self, name: str):
        with self._send(self._cmd_builder.eip712_send_struct_impl_root_struct(name)):
            self._enable_click_until_response()
        self._disable_click_until_response()
        return self._recv()

    def eip712_send_struct_impl_array(self, size: int):
        with self._send(self._cmd_builder.eip712_send_struct_impl_array(size)):
            pass
        return self._recv()

    def eip712_send_struct_impl_struct_field(self, raw_value: bytes):
        for apdu in self._cmd_builder.eip712_send_struct_impl_struct_field(raw_value):
            with self._send(apdu):
                self._enable_click_until_response()
            self._disable_click_until_response()
            assert self._recv().status == 0x9000

    def eip712_sign_new(self, bip32):
        with self._send(self._cmd_builder.eip712_sign_new(bip32)):
            if not self._settings[SettingType.VERBOSE_EIP712].value and \
               not self._eip712_filtering: # need to skip the message hash
                self._client.right_click()
                self._client.right_click()
            self._client.both_click() # approve signature
        resp = self._recv()
        assert resp.status == 0x9000
        return self._resp_parser.sign(resp.data)

    def eip712_sign_legacy(self,
                           bip32,
                           domain_hash: bytes,
                           message_hash: bytes):
        with self._send(self._cmd_builder.eip712_sign_legacy(bip32,
                                                             domain_hash,
                                                             message_hash)):
            self._client.right_click() # sign typed message screen
            for _ in range(2): # two hashes (domain + message)
                if self._client.firmware.device == "nanos":
                    screens_per_hash = 4
                else:
                    screens_per_hash = 2
                for _ in range(screens_per_hash):
                    self._client.right_click()
            self._client.both_click() # approve signature

        resp = self._recv()

        assert resp.status == 0x9000
        return self._resp_parser.sign(resp.data)

    def settings_set(self, new_values: Dict[SettingType, bool]):
        # Go to settings
        for _ in range(2):
            self._client.right_click()
        self._client.both_click()

        for enum in self._settings.keys():
            if self._client.firmware.device in self._settings[enum].devices:
                if enum in new_values.keys():
                    if new_values[enum] != self._settings[enum].value:
                        self._client.both_click()
                        self._settings[enum].value = new_values[enum]
                self._client.right_click()
        self._client.both_click()

    def eip712_filtering_activate(self):
        with self._send(self._cmd_builder.eip712_filtering_activate()):
            pass
        self._eip712_filtering = True
        assert self._recv().status == 0x9000

    def eip712_filtering_send_contract_name(self, name: str, sig: bytes):
        #pdb.set_trace()
        with self._send(self._cmd_builder.eip712_filtering_send_contract_name(name, sig)):
            self._enable_click_until_response()
        self._disable_click_until_response()
        assert self._recv().status == 0x9000

    def eip712_filtering_send_field_name(self, name: str, sig: bytes):
        with self._send(self._cmd_builder.eip712_filtering_send_field_name(name, sig)):
            pass
        assert self._recv().status == 0x9000
