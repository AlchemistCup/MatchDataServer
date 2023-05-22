@0x9e33122323e08be2;

interface Server {
    serverMethod @0 ();
    registerClient @1 (clientInterface :Client);
}

interface Client {
    clientMethod @0 ();
}