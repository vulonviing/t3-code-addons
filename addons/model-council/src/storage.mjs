export function createStorage(indexedDB) {
  let opening;
  const database = () => opening ??= new Promise((resolve, reject) => {
    const request = indexedDB.open('t3-adds-model-council', 1);
    request.onupgradeneeded = () => request.result.createObjectStore('jobs', { keyPath: 'id' });
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  const transact = async (mode, action) => {
    const db = await database();
    return new Promise((resolve, reject) => {
      const tx = db.transaction('jobs', mode);
      const request = action(tx.objectStore('jobs'));
      tx.oncomplete = () => resolve(request.result);
      tx.onabort = () => reject(tx.error ?? new Error('The council record could not be saved.'));
      tx.onerror = () => reject(tx.error);
    });
  };
  return {
    async save(job) {
      const db = await database();
      return new Promise((resolve, reject) => {
        const tx = db.transaction('jobs', 'readwrite'), store = tx.objectStore('jobs');
        const read = store.get(job.id);
        read.onsuccess = () => {
          // Cancellation from another window must survive stale worker writes.
          if (read.result?.cancelRequested) {
            job.cancelRequested = true;
            if (job.stage !== 'completed') job.stage = 'cancelled';
          }
          store.put(structuredClone(job));
        };
        tx.oncomplete = () => resolve();
        tx.onabort = () => reject(tx.error ?? new Error('The council record could not be saved.'));
        tx.onerror = () => reject(tx.error);
      });
    },
    all: () => transact('readonly', (store) => store.getAll()),
    get: (id) => transact('readonly', (store) => store.get(id)),
  };
}
