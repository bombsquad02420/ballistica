# Released under the MIT License. See LICENSE for details.

PCOMMAND = ../../tools/pcommand

all: sources

clean:
	rm -rf ../ballistica/generated ../../assets/src/ba_data/python/ba/_generated


# This section is generated by batools.metamakefile; do not edit by hand.
# __AUTOGENERATED_PUBLIC_BEGIN__

sources: \
  ../../assets/src/ba_data/python/ba/_generated/__init__.py \
  ../../assets/src/ba_data/python/ba/_generated/enums.py \
  ../ballistica/generated/python_embedded/binding.inc \
  ../ballistica/generated/python_embedded/bootstrap.inc

../ballistica/generated/python_embedded/binding.inc : bameta/python_embedded/binding.py ../../tools/batools/meta.py
	@$(PCOMMAND) gen_binding_code $< $@

../ballistica/generated/python_embedded/bootstrap.inc : bameta/python_embedded/bootstrap.py ../../tools/batools/meta.py
	@$(PCOMMAND) gen_flat_data_code $< $@ bootstrap_code

../../assets/src/ba_data/python/ba/_generated/__init__.py : ../../tools/batools/pcommand.py
	@$(PCOMMAND) gen_python_init_module $@

../../assets/src/ba_data/python/ba/_generated/enums.py : ../ballistica/core/types.h ../../tools/batools/pythonenumsmodule.py
	@$(PCOMMAND) gen_python_enums_module $< $@

# __AUTOGENERATED_PUBLIC_END__

# This section is generated by batools.metamakefile; do not edit by hand.
# __AUTOGENERATED_PRIVATE_BEGIN__

# Note: we include our public targets in efrocache even
# though they are buildable in public. This allows us to
# fetch them to bootstrap binary builds in cases where
# we can't use our full Makefiles (like Windows CI).

efrocache-list:
	@echo "../../assets/src/ba_data/python/ba/_generated/__init__.py" \
        "../../assets/src/ba_data/python/ba/_generated/enums.py" \
        "../ballistica/generated/python_embedded/binding.inc" \
        "../ballistica/generated/python_embedded/bootstrap.inc"

efrocache-build: sources

# __AUTOGENERATED_PRIVATE_END__
