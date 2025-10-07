from peewee import *
from orm import db_auth
import os.path
from orm import Auth
import gnupg

gpg = gnupg.GPG(gnupghome='gnup')


def CheckDBexists():
    if (not os.path.isfile('auth.db')):
        db_auth.connect()
        db_auth.create_tables([Auth])
        db_auth.close()


def AddUser(usuario, clave_publica):
    CheckDBexists()
    db_auth.connect()
    new_user = Auth(usuario=usuario, clave_publica=clave_publica)
    new_user.save()
    db_auth.commit()
    db_auth.close()


def GenerateSecretMessage(usuario, Mensage):
    db_auth.connect()
    clave_publica_armored = Auth.select().where(Auth.usuario == usuario).get().clave_publica
    db_auth.close()

    try:
        import_result = gpg.import_keys(clave_publica_armored)
        key_fingerprint = import_result.results[0]['fingerprint']

        encrypted_data = gpg.encrypt(
            Mensage,
            recipients=[key_fingerprint],
            always_trust=True,
            armor=True
        )

        if encrypted_data.ok:
            return str(encrypted_data)
        else:
            print(f"Error during encryption: {encrypted_data.status}")
            return None

    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None