"""Attack-family definitions for every label observed in the NSL-KDD data."""

from __future__ import annotations


ATTACK_FAMILY_BY_LABEL = {
    # Normal traffic
    "normal": "normal",
    # Denial of service
    "back": "dos",
    "land": "dos",
    "neptune": "dos",
    "pod": "dos",
    "smurf": "dos",
    "teardrop": "dos",
    "apache2": "dos",
    "mailbomb": "dos",
    "processtable": "dos",
    "udpstorm": "dos",
    "worm": "dos",
    # Probing and surveillance
    "ipsweep": "probe",
    "nmap": "probe",
    "portsweep": "probe",
    "satan": "probe",
    "mscan": "probe",
    "saint": "probe",
    # Remote-to-local attacks
    "ftp_write": "r2l",
    "guess_passwd": "r2l",
    "imap": "r2l",
    "multihop": "r2l",
    "phf": "r2l",
    "spy": "r2l",
    "warezclient": "r2l",
    "warezmaster": "r2l",
    "httptunnel": "r2l",
    "named": "r2l",
    "sendmail": "r2l",
    "snmpgetattack": "r2l",
    "snmpguess": "r2l",
    "xlock": "r2l",
    "xsnoop": "r2l",
    # User-to-root attacks
    "buffer_overflow": "u2r",
    "loadmodule": "u2r",
    "perl": "u2r",
    "rootkit": "u2r",
    "ps": "u2r",
    "sqlattack": "u2r",
    "xterm": "u2r",
}


def get_attack_family(label: str) -> str:
    """Normalize an NSL-KDD label and return its mapped attack family."""
    normalized_label = str(label).strip().lower()
    if normalized_label.endswith("."):
        normalized_label = normalized_label[:-1]

    try:
        return ATTACK_FAMILY_BY_LABEL[normalized_label]
    except KeyError as error:
        raise ValueError(
            f"Unmapped NSL-KDD label: {label!r} "
            f"(normalized as {normalized_label!r})"
        ) from error
