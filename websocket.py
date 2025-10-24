from common import sio

from packet import BasePacket, PacketFactory

@sio.on('connect')
def handle_connect():
    print('Client connected')
    # (Manda Packete Hola, Completamente inecesario pero me sirve para testear)
    welcome_packet = PacketFactory.create('welcome', {'message': 'Connected!'})
    sio.emit('packet', welcome_packet.to_dict())


Decrypted_message = 0
check = 0
# Maneja los paquetes entrantes, Solo muestra el tipo el la consola, si quieres usar el contenido, usa "data"
@sio.on('packet')
def handle_packet(data):
    global Decrypted_message
    global check
    packet = BasePacket(**data)
    print(f'Received packet type: {packet.type}')
    if ( packet.data[0] == 1 and check == 0):
        print(f'Creando Este weon: {packet.data[1]}');
        AddUser(packet.data[1], packet.data[2])
        message = str(random.randint(0, 2000000000))+str(random.randint(0, 2000000000)) + str(random.randint(0, 2000000000)) + str(random.randint(0, 2000000000))+ str(random.randint(0, 2000000000)) + str(random.randint(0, 2000000000)) + str(random.randint(0, 2000000000))
        Decrypted_message = message
        print(f'Mensage Secreto para resolver: {message}')
        import time
        time.sleep(0.5)
        mensage_encryptado = GenerateSecretMessage(packet.data[1], message)
        print(mensage_encryptado)
        payload = {
            "challenge": mensage_encryptado
        }
        Packete_Challenge = PacketFactory.create('challenge', payload)
        sio.emit('packet', Packete_Challenge.to_dict())
        check = 1
        print(check)
    if ( packet.data[0] == 2):
        print(f'Respeusta del Cliente: {packet.data[1]}')
        if ( packet.data[1] == Decrypted_message):
            print("Login Correcto")
            payload = {
                "answer": mensage_encryptado
            }
            Packete_Challenge = PacketFactory.create('chall_response', payload)
            sio.emit('packet', Packete_Challenge.to_dict())
    sio.emit('packet', packet.to_dict())
