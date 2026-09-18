package com.restomind.pos;

import android.os.Bundle;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {

    @Override
    public void onCreate(Bundle savedInstanceState) {
        // ANTES de super.onCreate: después el puente ya se armó y el plugin
        // no aparece en Capacitor.Plugins.
        registerPlugin(ImpresoraTermica.class);
        super.onCreate(savedInstanceState);
    }
}
