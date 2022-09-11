from multiprocessing import Process, Queue, Pool, Manager, RLock, Lock
import time
import random
import sys
    
deps1 = {1: {2, 3}, 3: {4, 5}, 6: {}}
deps = dict()

def f(i, todo, waiting, done, lock, deps):
    print('f: {0}'.format(i))
    while True:
        lock.acquire()
        if len(todo) == 0 and len(waiting) == 0:
            lock.release()
            break
        foundInWaiting = False
        foundInTodo = False
        for j in range(len(waiting)):
            val = waiting[j-1]
            print('Trying {0} from waiting in {1}'.format(val, i))
            prereqs = deps.get(val, set())
            print('prereqs: {0} in {1}'.format(prereqs, i))
            ok = True
            for x in prereqs:
                if x not in done:
                    ok = False
                    break
            if ok:
                foundInWaiting = True 
                del waiting[j-1]
                break
        if not foundInWaiting and len(todo) > 0:
            val = todo.pop(0)
            print('Trying {0} from todo in {1}'.format(val, i))
            foundInTodo = True
        lock.release()
        if not foundInWaiting and not foundInTodo:
            time.sleep(1)
        elif val in done:
            time.sleep(1)
        else:
            print('Running {0} in {1}'.format(val, i))
            time.sleep(0.5 * random.random())
            done.append(val)
            print('Value {0} is done in {1}'.format(val, i))
    print('{0} finished'.format(i))
    return i
    
def test():
    numProcesses = 7
    deps = deps1
    with Manager() as manager:
        todo = manager.list()
        waiting = manager.list()
        for i in range(1, 7):
            if i in deps:
                waiting.append(i)
            else:
                todo.append(i)
        print('todo: {0}'.format(todo))
        done = manager.list()
        lock = manager.Lock()
        # for i in range(numProcesses):
        #     Process(target=f, args=(i, todo, done, lock)).start()
        with Pool(processes=numProcesses) as pool:
            ress = [pool.apply_async(f, (i, todo, waiting, done, lock, deps)) for i in range(numProcesses)]
            print([res.get() for res in ress])
            #_ = res.get()
        sys.stdout.flush()
        print('Done: {0}'.format(done)) 
    
if __name__ == '__main__':
    test()