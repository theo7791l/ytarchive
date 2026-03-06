import asyncio
from typing import Optional, Callable
from datetime import datetime
import time

class DownloadQueueManager:
    """Gestionnaire global de queue de téléchargements pour éviter OOM"""
    
    def __init__(self, max_concurrent: int = 3, max_ram_mb: int = 150):
        """
        Args:
            max_concurrent: Nombre max de téléchargements simultanés
            max_ram_mb: RAM maximale disponible pour les downloads (en MB)
        """
        self.max_concurrent = max_concurrent
        self.max_ram_mb = max_ram_mb
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.active_downloads = 0
        self.waiting_downloads = 0
        self.lock = asyncio.Lock()
        self.download_stats = {}  # username -> stats
    
    def get_optimal_fragments(self) -> int:
        """Calcule le nombre optimal de fragments parallèles selon charge"""
        if self.active_downloads == 0:
            return 5  # Pleine vitesse si seul
        elif self.active_downloads == 1:
            return 4  # 2 utilisateurs = 4 fragments chacun
        elif self.active_downloads == 2:
            return 3  # 3 utilisateurs = 3 fragments chacun
        else:
            return 2  # 3+ utilisateurs = 2 fragments chacun (sécurité)
    
    def get_chunk_size_mb(self) -> int:
        """Calcule la taille optimale des chunks selon charge"""
        if self.active_downloads == 0:
            return 10  # 10MB si seul
        elif self.active_downloads == 1:
            return 8   # 8MB pour 2 utilisateurs
        elif self.active_downloads == 2:
            return 6   # 6MB pour 3 utilisateurs
        else:
            return 5   # 5MB pour 3+ utilisateurs
    
    async def acquire(self, username: str) -> dict:
        """Acquiert un slot de téléchargement (attend si queue pleine)"""
        async with self.lock:
            self.waiting_downloads += 1
            queue_position = self.waiting_downloads
        
        print(f"\n📊 [{username}] Position dans la queue: {queue_position}")
        print(f"   Downloads actifs: {self.active_downloads}/{self.max_concurrent}")
        
        if queue_position > 1:
            print(f"   ⏳ En attente... {queue_position - 1} avant vous")
        
        # Attendre un slot disponible
        await self.semaphore.acquire()
        
        async with self.lock:
            self.active_downloads += 1
            self.waiting_downloads -= 1
            
            # Calculer config optimale
            optimal_fragments = self.get_optimal_fragments()
            chunk_size_mb = self.get_chunk_size_mb()
            
            self.download_stats[username] = {
                'start_time': time.time(),
                'fragments': optimal_fragments,
                'chunk_size': chunk_size_mb
            }
            
            print(f"\n✅ [{username}] Slot acquis !")
            print(f"   Config adaptée: {optimal_fragments} fragments || {chunk_size_mb}MB chunks")
            print(f"   RAM estimée: ~{optimal_fragments * chunk_size_mb}MB")
            print(f"   Downloads actifs: {self.active_downloads}/{self.max_concurrent}\n")
            
            return {
                'max_parallel_fragments': optimal_fragments,
                'chunk_size_mb': chunk_size_mb,
                'position': 0,  # Plus en attente
                'active_downloads': self.active_downloads
            }
    
    async def release(self, username: str):
        """Libère un slot de téléchargement"""
        async with self.lock:
            self.active_downloads -= 1
            
            if username in self.download_stats:
                elapsed = time.time() - self.download_stats[username]['start_time']
                del self.download_stats[username]
                print(f"\n✅ [{username}] Download terminé en {elapsed:.1f}s")
            
            print(f"   Downloads actifs: {self.active_downloads}/{self.max_concurrent}")
            if self.waiting_downloads > 0:
                print(f"   👉 Prochain dans la queue: démarrage...\n")
        
        self.semaphore.release()
    
    def get_queue_status(self) -> dict:
        """Récupère le statut actuel de la queue"""
        return {
            'active_downloads': self.active_downloads,
            'max_concurrent': self.max_concurrent,
            'waiting_downloads': self.waiting_downloads,
            'available_slots': self.max_concurrent - self.active_downloads
        }

# Instance globale unique
_global_queue_manager = None

def get_queue_manager() -> DownloadQueueManager:
    """Récupère l'instance globale du queue manager"""
    global _global_queue_manager
    if _global_queue_manager is None:
        _global_queue_manager = DownloadQueueManager(
            max_concurrent=3,  # Max 3 downloads simultanés
            max_ram_mb=150     # 150MB de RAM max pour downloads
        )
    return _global_queue_manager
