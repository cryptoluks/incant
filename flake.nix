{
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  inputs.flake-utils.url = "github:numtide/flake-utils";

  outputs =
    { ... }@inputs:
    inputs.flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = import inputs.nixpkgs { inherit system; };
        
        pythonDeps = with pkgs.python3Packages; [
          black
          click
          jinja2
          mako
          pylint
          pyyaml
        ];

      in
      rec {
        # nix develop --command $SHELL
        devShells.default = pkgs.mkShell {
          packages = pythonDeps;
        };
      }
    );
}
