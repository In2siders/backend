from peewee import *
from orm import db_auth
import os.path
from orm import Auth
from pgpy import PGPKey, PGPUID, PGPMessage
import random

def CheckDBexists():
    if (not os.path.isfile('auth.db')):
        db_auth.connect()
        db_auth.create_tables([Auth])
        db_auth.save()
        db_auth.close()

def AddUser(usuario, clave_publica):
    db_auth.connect()
    new_user = Auth(usuario=usuario, clave_publica=clave_publica)
    new_user.save()
    db_auth.close()

def AuthenticateUser(usuario):
    CheckDBexists()
    db_auth.connect()
    clave_publica = Auth.select().where(Auth.usuario == usuario).get().clave_publica
    db_auth.close()
    message = str(random.randint(0, 2000000000))+str(random.randint(0, 2000000000)) + str(random.randint(0, 2000000000)) + str(random.randint(0, 2000000000))+ str(random.randint(0, 2000000000)) + str(random.randint(0, 2000000000)) + str(random.randint(0, 2000000000))
    PKey = PGPKey()
    PKey.parse(clave_publica)
    PGPmessage = PGPMessage.new(message)
    encrypted_message = PKey.encrypt(PGPmessage)

        
    