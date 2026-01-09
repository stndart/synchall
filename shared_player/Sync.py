from shared_player.playback.player import SyncPlayer


def main():
    player = SyncPlayer()

    uid = input("Enter room id: ")
    player.connect(uid)

    try:
        while True:
            com = input()
            if com.startswith("vol "):
                newvol = float(com[4:])
                if newvol > 1:
                    newvol /= 100
                newvol = max(min(newvol, 100), 0)
                player.playback.volume = newvol
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        player.close()
        pass


if __name__ == "__main__":
    main()
